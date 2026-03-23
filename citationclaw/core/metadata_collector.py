"""Multi-source metadata collector.

Queries OpenAlex, Semantic Scholar, and arXiv in parallel,
merges results by priority: OpenAlex > S2 > arXiv.
"""
import asyncio
from typing import Optional, List

from citationclaw.core.openalex_client import OpenAlexClient
from citationclaw.core.s2_client import S2Client
from citationclaw.core.arxiv_client import ArxivClient


class MetadataCollector:
    def __init__(self, email: Optional[str] = None, s2_api_key: Optional[str] = None):
        self.openalex = OpenAlexClient(email=email)
        self.s2 = S2Client(api_key=s2_api_key)
        self.arxiv = ArxivClient()

    async def collect(self, title: str) -> Optional[dict]:
        """Query OpenAlex + S2 + arXiv in parallel, merge results."""
        oa_result, s2_result, arxiv_result = await asyncio.gather(
            self.openalex.search_work(title),
            self.s2.search_paper(title),
            self.arxiv.search_paper(title),
            return_exceptions=True,
        )
        # Treat exceptions as None
        if isinstance(oa_result, Exception):
            oa_result = None
        if isinstance(s2_result, Exception):
            s2_result = None
        if isinstance(arxiv_result, Exception):
            arxiv_result = None
        return self._merge(oa_result, s2_result, arxiv_result)

    async def batch_collect(self, titles: List[str], concurrency: int = 10) -> List[Optional[dict]]:
        """Collect metadata for multiple papers concurrently."""
        sem = asyncio.Semaphore(concurrency)

        async def _collect(t):
            async with sem:
                return await self.collect(t)

        return await asyncio.gather(*[_collect(t) for t in titles])

    def _merge(self, oa: Optional[dict], s2: Optional[dict], arxiv: Optional[dict]) -> Optional[dict]:
        """Merge by priority: OpenAlex > S2 > arXiv, with cross-source author enrichment."""
        primary = oa or s2 or arxiv
        if primary is None:
            return None

        result = {
            "title": primary.get("title", ""),
            "year": primary.get("year"),
            "doi": primary.get("doi", ""),
            "cited_by_count": primary.get("cited_by_count", 0),
            "sources": [],
        }

        # Tag sources
        if oa:
            result["sources"].append("openalex")
            result["openalex_id"] = oa.get("openalex_id", "")
        if s2:
            result["sources"].append("s2")
            result["s2_id"] = s2.get("s2_id", "")
        if arxiv:
            result["sources"].append("arxiv")
            result["arxiv_id"] = arxiv.get("arxiv_id", "")

        # Merge authors: start with OpenAlex, enrich with S2 ids, fallback to arXiv
        oa_authors = oa.get("authors", []) if oa else []
        s2_authors = s2.get("authors", []) if s2 else []
        arxiv_authors = arxiv.get("authors", []) if arxiv else []
        merged_authors = self._merge_authors(oa_authors, s2_authors)
        # If still no authors, use arXiv
        if not merged_authors and arxiv_authors:
            merged_authors = arxiv_authors
        result["authors"] = merged_authors

        # S2 supplements: influential citation count
        result["influential_citation_count"] = (
            s2.get("influential_citation_count", 0) if s2 else 0
        )

        # PDF URL: prefer arXiv (reliable), then S2
        pdf_url = ""
        if arxiv and arxiv.get("pdf_url"):
            pdf_url = arxiv["pdf_url"]
        elif s2 and s2.get("pdf_url"):
            pdf_url = s2["pdf_url"]
        result["pdf_url"] = pdf_url

        return result

    @staticmethod
    def _merge_authors(oa_authors: list, s2_authors: list) -> list:
        """Merge author lists from OpenAlex and S2, filling gaps from each other.

        Strategy:
        - If OpenAlex has authors: use as base, enrich with S2 s2_id
        - If OpenAlex has no authors: use S2 authors
        - For each OA author missing affiliation: try to find match in S2 by name
        """
        if not oa_authors and not s2_authors:
            return []
        if not oa_authors:
            return s2_authors
        if not s2_authors:
            return oa_authors

        # Build S2 name lookup (lowercase → author dict)
        s2_by_name = {}
        for a in s2_authors:
            name = a.get("name", "").strip().lower()
            if name:
                s2_by_name[name] = a
                # Also index by last name for fuzzy matching
                parts = name.split()
                if len(parts) >= 2:
                    s2_by_name[parts[-1]] = a  # last name

        # Enrich OA authors with S2 data
        merged = []
        for a in oa_authors:
            enriched = dict(a)  # copy
            name_lower = a.get("name", "").strip().lower()

            # Try to find S2 match
            s2_match = s2_by_name.get(name_lower)
            if not s2_match:
                # Try last name match
                parts = name_lower.split()
                if parts:
                    s2_match = s2_by_name.get(parts[-1])

            if s2_match:
                # Fill s2_id (for later Author API queries)
                if not enriched.get("s2_id") and s2_match.get("s2_id"):
                    enriched["s2_id"] = s2_match["s2_id"]

            merged.append(enriched)

        return merged

    async def close(self):
        await self.openalex.close()
        await self.s2.close()
        await self.arxiv.close()
