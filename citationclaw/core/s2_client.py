"""Semantic Scholar API client for academic metadata.

API docs: https://api.semanticscholar.org/
Free tier: 1 req/s without key, higher with API key.
Unique fields: h_index, influentialCitationCount.
"""
import asyncio
from typing import Optional, List, Iterable
from urllib.parse import quote

from citationclaw.core.http_utils import make_async_client

BASE_URL = "https://api.semanticscholar.org/graph/v1"

S2_PAPER_FIELDS = ",".join([
    "title", "year", "citationCount", "influentialCitationCount",
    "authors", "venue", "abstract", "externalIds", "publicationDate",
    "fieldsOfStudy", "referenceCount", "openAccessPdf", "publicationVenue",
    "journal", "isOpenAccess",
])

S2_LIGHT_FIELDS = (
    "citingPaper.paperId,citingPaper.title,"
    "citingPaper.citationCount,citingPaper.year"
)

S2_RICH_FIELDS = ",".join([
    "contexts", "intents", "contextsWithIntent", "isInfluential",
    "citingPaper.paperId", "citingPaper.title",
    "citingPaper.citationCount", "citingPaper.year",
    "citingPaper.externalIds",
])

_s2_global_sem: Optional[asyncio.Semaphore] = None  # Initialized per-client


class S2Client:
    def __init__(self, api_key: Optional[str] = None):
        global _s2_global_sem
        self._client = make_async_client(timeout=30.0)
        self._has_key = bool(api_key)
        self.used_anonymous_fallback = False
        if api_key:
            self._client.headers["x-api-key"] = api_key
            self._rate_delay = 0.4  # With key: ~2.5 req/s per slot
            if _s2_global_sem is None:
                _s2_global_sem = asyncio.Semaphore(2)  # 2 concurrent × 0.4s = ~5 req/s
        else:
            self._rate_delay = 1.1  # Free tier: 1 req/s
            if _s2_global_sem is None:
                _s2_global_sem = asyncio.Semaphore(1)

    def _switch_to_anonymous(self) -> bool:
        global _s2_global_sem
        if not self._has_key:
            return False
        self._client.headers.pop("x-api-key", None)
        self._has_key = False
        self.used_anonymous_fallback = True
        self._rate_delay = 1.1
        _s2_global_sem = asyncio.Semaphore(1)
        return True

    async def search_paper(self, title: str) -> Optional[dict]:
        data = await self._get_json(
            "/paper/search",
            {"query": title, "limit": 1, "fields": S2_PAPER_FIELDS},
            retries=3,
        )
        results = data.get("data", []) if data else []
        return self._parse_paper(results[0]) if results else None

    async def _get_json(self, path: str, params: Optional[dict] = None, retries: int = 4):
        url = f"{BASE_URL}{path}"
        for attempt in range(retries):
            async with _s2_global_sem:
                await asyncio.sleep(self._rate_delay)
                try:
                    resp = await self._client.get(url, params=params)
                except Exception:
                    await asyncio.sleep(3)
                    continue
            if resp.status_code == 429:
                await asyncio.sleep(5 * (attempt + 1))
                continue
            if resp.status_code in (401, 403) and self._switch_to_anonymous():
                continue
            if resp.status_code == 404:
                return None
            if resp.status_code != 200:
                await asyncio.sleep(3)
                continue
            return resp.json()
        return None

    async def _post_json(
        self,
        path: str,
        body: dict,
        params: Optional[dict] = None,
        retries: int = 4,
    ):
        url = f"{BASE_URL}{path}"
        for attempt in range(retries):
            async with _s2_global_sem:
                await asyncio.sleep(self._rate_delay)
                try:
                    resp = await self._client.post(url, json=body, params=params)
                except Exception:
                    await asyncio.sleep(3)
                    continue
            if resp.status_code == 429:
                await asyncio.sleep(5 * (attempt + 1))
                continue
            if resp.status_code in (401, 403) and self._switch_to_anonymous():
                continue
            if resp.status_code != 200:
                await asyncio.sleep(3)
                continue
            return resp.json()
        return None

    async def search_match(self, title: str) -> Optional[dict]:
        data = await self._get_json(
            "/paper/search/match",
            {"query": title, "fields": S2_PAPER_FIELDS},
        )
        return data["data"][0] if data and data.get("data") else None

    async def search(self, query: str, limit: int = 5) -> Optional[dict]:
        data = await self._get_json(
            "/paper/search",
            {"query": query, "limit": limit, "fields": S2_PAPER_FIELDS},
        )
        return data["data"][0] if data and data.get("data") else None

    async def get_paper(self, paper_id: str) -> Optional[dict]:
        return await self._get_json(f"/paper/{paper_id}", {"fields": S2_PAPER_FIELDS})

    async def batch_papers(self, paper_ids: Iterable[str]) -> dict:
        ids = [pid for pid in paper_ids if pid]
        results = {}
        for i in range(0, len(ids), 500):
            batch = ids[i:i + 500]
            data = await self._post_json(
                "/paper/batch",
                {"ids": batch},
                {"fields": S2_PAPER_FIELDS},
            )
            if not data:
                continue
            for paper in data:
                if paper and paper.get("paperId"):
                    results[paper["paperId"]] = paper
        return results

    async def get_citations_light(self, paper_id: str, scan_cap: int = 3000) -> list:
        items = []
        offset = 0
        while len(items) < scan_cap:
            data = await self._get_json(
                f"/paper/{paper_id}/citations",
                {"fields": S2_LIGHT_FIELDS, "limit": 1000, "offset": offset},
            )
            if not data:
                break
            batch = data.get("data") or []
            items.extend(batch)
            if data.get("next") is None or len(batch) < 1000:
                break
            offset = data["next"]
            if offset >= min(scan_cap, 9500):
                break
        return items[:scan_cap]

    async def get_citation_contexts(self, paper_id: str, target_ids: set[str]) -> dict:
        contexts = {}
        if not target_ids:
            return contexts
        offset = 0
        while True:
            data = await self._get_json(
                f"/paper/{paper_id}/citations",
                {"fields": S2_RICH_FIELDS, "limit": 500, "offset": offset},
            )
            if not data:
                break
            for item in data.get("data") or []:
                citing = (item or {}).get("citingPaper") or {}
                pid = citing.get("paperId")
                if pid and pid in target_ids:
                    contexts[pid] = {
                        "contexts": item.get("contexts") or [],
                        "intents": item.get("intents") or [],
                        "contextsWithIntent": item.get("contextsWithIntent") or [],
                        "isInfluential": item.get("isInfluential") or False,
                    }
            if len(contexts) >= len(target_ids):
                break
            if data.get("next") is None or len(data.get("data") or []) < 500:
                break
            offset = data["next"]
            if offset >= 9500:
                break
        return contexts

    @staticmethod
    def _titles_match(query: str, result: str, threshold: float = 0.45) -> bool:
        """Check title similarity by word overlap.

        Threshold lowered from 0.7 to 0.45 (PaperRadar uses no validation at all).
        Handles: Chinese titles, abbreviations, minor variations.
        """
        import re as _re
        _stop = {'a', 'an', 'the', 'of', 'in', 'on', 'for', 'and', 'or', 'to',
                 'with', 'by', 'is', 'are', 'from', 'at', 'as', 'its', 'via', 'using'}

        # If query contains Chinese chars, S2 may return English translation
        # → accept if any significant word matches (very lenient for cross-language)
        has_cjk = any('\u4e00' <= c <= '\u9fff' for c in query)
        if has_cjk:
            # Extract any English/pinyin words from both
            q_eng = set(_re.findall(r'[a-zA-Z]{3,}', query.lower()))
            r_eng = set(_re.findall(r'[a-zA-Z]{3,}', result.lower()))
            if q_eng and r_eng:
                return len(q_eng & r_eng) >= 1  # Any shared English word
            return True  # Can't compare → accept (let user verify)

        q_words = set(_re.sub(r'[^\w\s]', ' ', query.lower()).split()) - _stop
        r_words = set(_re.sub(r'[^\w\s]', ' ', result.lower()).split()) - _stop
        if not q_words:
            return True
        if len(q_words) <= 3:
            return len(q_words & r_words) >= 1
        return len(q_words & r_words) / len(q_words) >= threshold

    async def search_by_url(self, paper_url: str) -> Optional[dict]:
        """Search S2 by external URL (paper_link from GS).

        S2 supports: /paper/URL:{encoded_url}?fields=...
        This works for IEEE, arXiv, ACM, Springer etc. URLs.
        """
        if not paper_url:
            return None
        fields = "title,year,authors,citationCount,influentialCitationCount,externalIds,openAccessPdf,venue,publicationVenue,journal"
        encoded = quote(paper_url, safe='')
        data = await self._get_json(
            f"/paper/URL:{encoded}",
            {"fields": fields},
        )
        if not data:
            return None
        try:
            return self._parse_paper(data)
        except Exception:
            return None

    async def get_author(self, author_id: str) -> Optional[dict]:
        data = await self._get_json(
            f"/author/{author_id}",
            {"fields": "name,hIndex,citationCount,affiliations"},
        )
        if not data:
            return None
        return self._parse_author(data)

    def _build_search_url(self, title: str) -> str:
        # NOTE: Do NOT include authors.affiliations — it causes S2 to return empty author names!
        # Affiliations are supplemented later from OpenAlex or PDF extraction.
        return f"{BASE_URL}/paper/search?query={quote(title)}&limit=1&fields={S2_PAPER_FIELDS}"

    def _parse_paper(self, paper: dict) -> dict:
        authors = []
        for author in paper.get("authors", []):
            # Don't request authors.affiliations — it breaks author name!
            # Affiliations supplemented from OpenAlex or PDF later.
            authors.append({
                "name": author.get("name", ""),
                "s2_id": author.get("authorId", ""),
                "affiliation": "",
            })
        ext_ids = paper.get("externalIds", {}) or {}
        pdf_info = paper.get("openAccessPdf") or {}
        venue = (paper.get("venue", "")
                 or (paper.get("publicationVenue") or {}).get("name", "")
                 or (paper.get("journal") or {}).get("name", ""))

        # PDF URL fallback chain (PaperRadar-style: construct at metadata stage)
        arxiv_id = ext_ids.get("ArXiv", "")
        doi = ext_ids.get("DOI", "")
        pdf_url = pdf_info.get("url", "")
        if not pdf_url and arxiv_id:
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
        if not pdf_url and doi:
            pdf_url = f"https://doi.org/{doi}"

        return {
            "title": paper.get("title", ""),
            "year": paper.get("year"),
            "doi": doi,
            "arxiv_id": arxiv_id,
            "cited_by_count": paper.get("citationCount", 0),
            "influential_citation_count": paper.get("influentialCitationCount", 0),
            "s2_id": paper.get("paperId", ""),
            "authors": authors,
            "pdf_url": pdf_url,
            "venue": venue,
            "_external_ids": ext_ids,
            "source": "s2",
        }

    def _parse_author(self, author: dict) -> dict:
        affiliations = author.get("affiliations", [])
        return {
            "name": author.get("name", ""),
            "s2_id": author.get("authorId", ""),
            "h_index": author.get("hIndex", 0),
            "citation_count": author.get("citationCount", 0),
            "affiliation": affiliations[0] if affiliations else "",
            "source": "s2",
        }

    async def close(self):
        await self._client.aclose()
