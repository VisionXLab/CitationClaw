from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from citationclaw.core.arxiv_client import ArxivClient
from citationclaw.core.s2_client import S2Client
from citationclaw.skills.base import SkillContext, SkillResult


SCAN_CAP = 3000


class S2CitationFetchSkill:
    name = "phase1_s2_citation_fetch"

    async def run(self, ctx: SkillContext, **kwargs) -> SkillResult:
        title: str = kwargs["title"]
        output_file = Path(kwargs["output_file"])
        scan_cap: int = int(kwargs.get("scan_cap") or SCAN_CAP)

        client = S2Client(api_key=getattr(ctx.config, "s2_api_key", None))
        arxiv = ArxivClient()
        try:
            ctx.log(f"[S2 Phase1] searching seed: {title[:80]}")
            seed = await self._find_seed(client, arxiv, title)
            if client.used_anonymous_fallback:
                ctx.log(
                    "[S2 Phase1] configured API key was rejected; "
                    "continuing with anonymous S2 access"
                )
            if not seed or not seed.get("paperId"):
                output_file.parent.mkdir(parents=True, exist_ok=True)
                output_file.write_text("", encoding="utf-8")
                ctx.log(f"[S2 Phase1] seed not found: {title[:80]}")
                return SkillResult(
                    name=self.name,
                    data={"output_file": str(output_file), "total": 0, "seed": None},
                )

            seed_id = seed["paperId"]
            ctx.log(
                f"[S2 Phase1] seed matched: {seed.get('title', title)[:80]} "
                f"({seed.get('year') or '?'})"
            )

            light = await client.get_citations_light(seed_id, scan_cap=scan_cap)
            light = [
                item for item in light
                if (item.get("citingPaper") or {}).get("paperId")
            ]
            light.sort(
                key=lambda item: -((item.get("citingPaper") or {}).get("citationCount") or 0)
            )
            if ctx.cancel_check and ctx.cancel_check():
                return SkillResult(
                    name=self.name,
                    data={"output_file": str(output_file), "total": 0, "cancelled": True},
                )

            citing_ids = [
                (item.get("citingPaper") or {}).get("paperId")
                for item in light
                if (item.get("citingPaper") or {}).get("paperId")
            ]
            ctx.log(f"[S2 Phase1] scanned {len(citing_ids)} citing papers")

            details = await client.batch_papers(citing_ids)
            ctx.log(f"[S2 Phase1] fetched details for {len(details)} papers")

            contexts = await client.get_citation_contexts(seed_id, set(citing_ids))
            ctx.log(f"[S2 Phase1] fetched S2 contexts for {len(contexts)} edges")

            written = self._write_output(
                output_file=output_file,
                seed=seed,
                light_items=light,
                details=details,
                contexts=contexts,
                target_title=title,
                progress=ctx.progress,
            )
            return SkillResult(
                name=self.name,
                data={
                    "output_file": str(output_file),
                    "total": written,
                    "seed": {
                        "paperId": seed_id,
                        "title": seed.get("title", title),
                        "year": seed.get("year"),
                        "citationCount": seed.get("citationCount", 0),
                    },
                },
            )
        finally:
            await client.close()
            await arxiv.close()

    async def _find_seed(
        self,
        client: S2Client,
        arxiv: ArxivClient,
        title: str,
    ) -> Optional[dict]:
        seed = await client.search_match(title)
        if seed:
            return seed
        seed = await client.search(title)
        if seed:
            return seed
        arxiv_hit = await arxiv.search_paper(title)
        arxiv_id = (arxiv_hit or {}).get("arxiv_id")
        if arxiv_id:
            return await client.get_paper(f"ArXiv:{arxiv_id}")
        return None

    def _write_output(
        self,
        *,
        output_file: Path,
        seed: dict,
        light_items: list,
        details: dict,
        contexts: dict,
        target_title: str,
        progress=None,
    ) -> int:
        paper_dict = {}
        total = len(light_items)
        for idx, item in enumerate(light_items):
            citing_light = item.get("citingPaper") or {}
            pid = citing_light.get("paperId")
            if not pid:
                continue
            paper = details.get(pid) or citing_light
            ctx = contexts.get(pid) or {}
            paper_dict[f"paper_{idx}"] = self._to_phase1_paper(
                paper=paper,
                light=citing_light,
                context=ctx,
                seed=seed,
                target_title=target_title,
            )
            if progress:
                progress(idx + 1, total)

        output = {
            "page_0": {
                "source": "s2",
                "seed_paper": {
                    "paperId": seed.get("paperId", ""),
                    "title": seed.get("title", target_title),
                    "year": seed.get("year"),
                    "citationCount": seed.get("citationCount", 0),
                },
                "paper_dict": paper_dict,
            }
        }
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(json.dumps(output, ensure_ascii=False) + "\n", encoding="utf-8")
        return len(paper_dict)

    def _to_phase1_paper(
        self,
        *,
        paper: dict,
        light: dict,
        context: dict,
        seed: dict,
        target_title: str,
    ) -> dict:
        metadata = self._paper_to_metadata(paper)
        authors = {}
        for i, author in enumerate(metadata.get("authors", [])):
            name = author.get("name", "").strip()
            if not name:
                continue
            aid = author.get("s2_id", "")
            authors[f"author_{i}_{name}"] = (
                f"https://www.semanticscholar.org/author/{aid}" if aid else ""
            )

        return {
            "paper_title": metadata.get("title") or light.get("title", ""),
            "paper_link": self._paper_link(metadata),
            "paper_year": metadata.get("year") or light.get("year"),
            "citation": str(metadata.get("cited_by_count") or light.get("citationCount") or 0),
            "authors": authors,
            "gs_pdf_link": "",
            "gs_all_versions": "",
            "source": "s2",
            "s2_id": metadata.get("s2_id", ""),
            "doi": metadata.get("doi", ""),
            "arxiv_id": metadata.get("arxiv_id", ""),
            "venue": metadata.get("venue", ""),
            "pdf_url": metadata.get("pdf_url", ""),
            "s2_contexts": context.get("contexts") or [],
            "s2_intents": context.get("intents") or [],
            "s2_contextsWithIntent": context.get("contextsWithIntent") or [],
            "s2_isInfluential": context.get("isInfluential") or False,
            "s2_citing_paper": seed.get("title", target_title),
            "s2_cited_paper_id": seed.get("paperId", ""),
            "s2_metadata": metadata,
        }

    @staticmethod
    def _paper_to_metadata(paper: dict) -> dict:
        ext_ids = paper.get("externalIds") or {}
        pdf_info = paper.get("openAccessPdf") or {}
        arxiv_id = ext_ids.get("ArXiv", "")
        doi = ext_ids.get("DOI", "")
        pdf_url = pdf_info.get("url", "")
        if not pdf_url and arxiv_id:
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
        if not pdf_url and doi:
            pdf_url = f"https://doi.org/{doi}"

        venue = (
            paper.get("venue", "")
            or (paper.get("publicationVenue") or {}).get("name", "")
            or (paper.get("journal") or {}).get("name", "")
        )
        authors = []
        for author in paper.get("authors") or []:
            authors.append({
                "name": author.get("name", ""),
                "s2_id": author.get("authorId", ""),
                "affiliation": "",
                "source": "s2",
            })

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
            "oa_pdf_url": "",
            "venue": venue,
            "sources": ["s2_phase1"],
            "_external_ids": ext_ids,
        }

    @staticmethod
    def _paper_link(metadata: dict) -> str:
        if metadata.get("doi"):
            return f"https://doi.org/{metadata['doi']}"
        if metadata.get("arxiv_id"):
            return f"https://arxiv.org/abs/{metadata['arxiv_id']}"
        if metadata.get("s2_id"):
            return f"https://www.semanticscholar.org/paper/{metadata['s2_id']}"
        return ""
