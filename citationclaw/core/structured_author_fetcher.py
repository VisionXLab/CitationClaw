"""Structured author fetching: WOS → S2 fallback → MinerU affiliation supplement."""
from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

from citationclaw.core.author_name_utils import format_wos_name, name_keys, to_natural_name
from citationclaw.core.s2_client import S2Client


_WOS_ENDPOINT = "https://api.clarivate.com/apis/wos-starter/v1/documents"


def _normalize_title(text: str) -> str:
    import unicodedata
    text = unicodedata.normalize("NFKD", text or "").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _wos_hit_authors(hit: dict) -> list[dict[str, Any]]:
    names = hit.get("names", {}) or {}
    authors = []
    for a in names.get("authors", []) or []:
        raw = (a.get("wosStandard", "") or a.get("displayName", "")).strip()
        name = to_natural_name(format_wos_name(raw) or raw)
        if name:
            authors.append({"name": name, "affiliation": "", "email": "", "source": "wos"})
    return authors


async def _query_wos(
    api_key: str,
    title: str,
    doi: str,
    *,
    retries: int = 2,
    retry_wait: float = 20.0,
) -> list[dict[str, Any]]:
    """Query WOS Starter API; returns author list (empty on failure or not found)."""
    if not api_key:
        return []
    query = f"DO=({doi})" if doi else f'TI=("{title}")'
    params = {"db": "WOS", "q": query, "limit": 5, "page": 1}
    headers = {"X-ApiKey": api_key}

    for attempt in range(retries + 1):
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.get(
                    f"{_WOS_ENDPOINT}?{urlencode(params)}", headers=headers
                )
                resp.raise_for_status()
                hits = resp.json().get("hits", []) or []
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429 and attempt < retries:
                await asyncio.sleep(retry_wait * (attempt + 1))
                continue
            return []
        except Exception:
            if attempt < retries:
                await asyncio.sleep(10.0)
                continue
            return []

        if not hits:
            return []
        # DOI match preferred; fallback to first title-equal hit
        title_norm = _normalize_title(title)
        best = None
        for h in hits:
            ids = h.get("identifiers", {}) or {}
            if doi and (ids.get("doi") or "").lower() == doi.lower():
                best = h
                break
        if best is None:
            for h in hits:
                if _normalize_title(h.get("title", "")) == title_norm:
                    best = h
                    break
        if best is None:
            best = hits[0]
        return _wos_hit_authors(best)
    return []


async def _query_s2(s2_client: S2Client, title: str) -> list[dict[str, Any]]:
    result = await s2_client.search_paper(title)
    if not result:
        return []
    authors = []
    for a in result.get("authors", []):
        raw = a.get("name", "")
        name = to_natural_name(format_wos_name(raw) or raw)
        if name:
            authors.append({
                "name": name,
                "affiliation": a.get("affiliation", ""),
                "email": "",
                "s2_id": a.get("s2_id", ""),
                "source": "s2",
            })
    return authors


def _merge_wos_s2(
    wos_authors: list[dict[str, Any]],
    s2_authors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Enrich WOS author list with S2 affiliation/s2_id via name matching.

    WOS is authoritative for the author list; S2 fills in missing affiliations.
    Names are matched with names_match() which handles initials, accents, and
    different formatting conventions (WOS abbreviated ↔ S2 full names).
    """
    from citationclaw.core.author_name_utils import names_match

    if not s2_authors:
        return wos_authors
    if not wos_authors:
        return s2_authors

    matched_s2_ids: set[int] = set()
    merged: list[dict[str, Any]] = []

    for wos_a in wos_authors:
        enriched = dict(wos_a)
        for s2_a in s2_authors:
            if names_match(wos_a.get("name", ""), s2_a.get("name", "")):
                matched_s2_ids.add(id(s2_a))
                if s2_a.get("affiliation") and not enriched.get("affiliation"):
                    enriched["affiliation"] = s2_a["affiliation"]
                    enriched["affiliation_source"] = "s2"
                if s2_a.get("s2_id") and not enriched.get("s2_id"):
                    enriched["s2_id"] = s2_a["s2_id"]
                if s2_a.get("openalex_id") and not enriched.get("openalex_id"):
                    enriched["openalex_id"] = s2_a["openalex_id"]
                break
        merged.append(enriched)

    return [a for a in merged if a.get("name")]


def _merge_with_pdf(
    api_authors: list[dict[str, Any]],
    pdf_authors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Enrich api_authors with affiliations from pdf_authors; append unmatched PDF authors."""
    if not pdf_authors:
        return api_authors
    if not api_authors:
        return [{"name": to_natural_name(a.get("name", "")), "affiliation": a.get("affiliation", ""),
                 "email": a.get("email", ""), "source": "pdf"} for a in pdf_authors]

    pdf_by_key: dict[str, dict] = {}
    for a in pdf_authors:
        for k in name_keys(a.get("name", "")):
            pdf_by_key.setdefault(k, a)

    matched_ids: set[int] = set()
    merged = []
    for api_a in api_authors:
        enriched = dict(api_a)
        match = None
        for k in name_keys(api_a.get("name", "")):
            if k in pdf_by_key:
                match = pdf_by_key[k]
                matched_ids.add(id(match))
                break
        if match:
            if match.get("affiliation") and not enriched.get("affiliation"):
                enriched["affiliation"] = match["affiliation"]
            if match.get("email") and not enriched.get("email"):
                enriched["email"] = match["email"]
        merged.append(enriched)

    for pdf_a in pdf_authors:
        if id(pdf_a) not in matched_ids:
            merged.append({
                "name": to_natural_name(pdf_a.get("name", "")),
                "affiliation": pdf_a.get("affiliation", ""),
                "email": pdf_a.get("email", ""),
                "source": "pdf_only",
            })
    return [a for a in merged if a.get("name")]


class StructuredAuthorFetcher:
    """Fetch structured author list: WOS → S2 fallback → MinerU affiliation supplement.

    All returned names are in natural format ("First Last", no comma).
    """

    def __init__(
        self,
        wos_api_key: str = "",
        s2_api_key: str = "",
        mineru_api_token: str = "",
        openai_api_key: str = "",
        openai_base_url: str = "",
        model: str = "",
        pdf_cache_dir: str | Path | None = None,
        log_callback=None,
    ):
        self._wos_key = wos_api_key
        self._s2_client = S2Client(api_key=s2_api_key) if s2_api_key or True else None
        self._mineru_token = mineru_api_token
        self._openai_key = openai_api_key
        self._openai_base = openai_base_url
        self._model = model
        self._pdf_cache_dir = Path(pdf_cache_dir) if pdf_cache_dir else None
        self._log = log_callback or (lambda msg: None)

    async def fetch(
        self,
        title: str,
        doi: str = "",
        pdf_path: str | Path | None = None,
    ) -> tuple[list[dict[str, Any]], str]:
        """Return (author_list, source_label).

        source_label: "wos" | "s2" | "pdf" | "" (empty = no authors found)
        """
        # Step 1: WOS
        wos_authors: list[dict] = []
        if self._wos_key:
            try:
                wos_authors = await _query_wos(self._wos_key, title, doi)
            except Exception as exc:
                self._log(f"[StructuredAuthorFetcher] WOS error: {exc}")

        # Step 2: PDF (MinerU) — try to get affiliations from PDF
        pdf_authors: list[dict] = []
        pdf_path_resolved = Path(pdf_path) if pdf_path else None
        if pdf_path_resolved and pdf_path_resolved.exists() and self._openai_key:
            try:
                pdf_authors = await self._run_mineru(pdf_path_resolved, title, doi)
            except Exception as exc:
                self._log(f"[StructuredAuthorFetcher] MinerU error: {exc}")

        if wos_authors:
            if pdf_authors:
                # WOS + PDF: enrich WOS names with PDF affiliations
                merged = _merge_with_pdf(wos_authors, pdf_authors)
                self._log(
                    f"[StructuredAuthorFetcher] WOS {len(wos_authors)} + PDF {len(pdf_authors)}"
                    f" → merged {len(merged)} authors"
                )
                return merged, "wos+pdf"
            else:
                # WOS succeeded but no PDF — fall back to S2 for affiliations
                s2_authors: list[dict] = []
                if self._s2_client:
                    try:
                        s2_authors = await _query_s2(self._s2_client, title)
                    except Exception as exc:
                        self._log(f"[StructuredAuthorFetcher] S2 error: {exc}")
                if s2_authors:
                    merged = _merge_wos_s2(wos_authors, s2_authors)
                    self._log(
                        f"[StructuredAuthorFetcher] WOS {len(wos_authors)} + S2 {len(s2_authors)}"
                        f" → merged {len(merged)} authors"
                    )
                    return merged, "wos+s2"
                else:
                    return wos_authors, "wos"

        # WOS failed — fall back to S2
        s2_authors: list[dict] = []
        if self._s2_client:
            try:
                s2_authors = await _query_s2(self._s2_client, title)
            except Exception as exc:
                self._log(f"[StructuredAuthorFetcher] S2 error: {exc}")

        if s2_authors:
            if pdf_authors:
                merged = _merge_with_pdf(s2_authors, pdf_authors)
                return merged, "s2+pdf"
            return s2_authors, "s2"

        if pdf_authors:
            return [{"name": to_natural_name(a.get("name", "")), "affiliation": a.get("affiliation", ""),
                     "email": a.get("email", ""), "source": "pdf"} for a in pdf_authors], "pdf"

        return [], ""

    async def _run_mineru(self, pdf_path: Path, title: str, doi: str) -> list[dict]:
        from citationclaw.core.pdf_mineru_parser import MinerUParser
        from citationclaw.core.pdf_author_extractor import PDFAuthorExtractor

        cache_dir = self._pdf_cache_dir or (pdf_path.parent / ".pdf_parsed_cache")
        parser = MinerUParser(output_base=cache_dir, mineru_api_token=self._mineru_token)
        extractor = PDFAuthorExtractor(
            api_key=self._openai_key,
            base_url=self._openai_base,
            model=self._model,
        )
        paper_key = parser.paper_key({"doi": doi, "title": title or pdf_path.stem})
        parsed = await parser.parse_async(pdf_path, paper_key)
        if not parsed:
            return []
        blocks = parsed.get("content_list") or parsed.get("first_page_blocks", [])
        return await extractor.extract(blocks)
