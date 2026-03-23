"""OpenAlex API client for structured academic metadata.

API docs: https://docs.openalex.org/
Free, no key required, recommend <10 req/s.
"""
import asyncio
from typing import Optional, List
from urllib.parse import quote

from citationclaw.core.http_utils import make_async_client

BASE_URL = "https://api.openalex.org"

class OpenAlexClient:
    def __init__(self, email: Optional[str] = None):
        self._params = {"mailto": email} if email else {}
        self._client = make_async_client(timeout=30.0)

    async def search_work(self, title: str) -> Optional[dict]:
        url = self._build_search_url(title)
        resp = await self._client.get(url, params=self._params)
        if resp.status_code != 200:
            return None
        data = resp.json()
        results = data.get("results", [])
        if not results:
            return None
        parsed = self._parse_work(results[0])
        # Validate title similarity to avoid returning wrong papers
        if not self._titles_match(title, parsed.get("title", "")):
            return None
        return parsed

    @staticmethod
    def _titles_match(query: str, result: str, threshold: float = 0.5) -> bool:
        """Check if result title is similar enough to query (word overlap)."""
        import re as _re
        q_words = set(_re.sub(r'[^\w\s]', ' ', query.lower()).split())
        r_words = set(_re.sub(r'[^\w\s]', ' ', result.lower()).split())
        if not q_words:
            return False
        return len(q_words & r_words) / len(q_words) >= threshold

    async def get_author(self, author_id: str) -> Optional[dict]:
        url = f"{BASE_URL}/authors/{author_id}"
        resp = await self._client.get(url, params=self._params)
        if resp.status_code != 200:
            return None
        return self._parse_author(resp.json())

    async def batch_search_works(self, titles: List[str], concurrency: int = 10) -> List[Optional[dict]]:
        sem = asyncio.Semaphore(concurrency)
        async def _search(t):
            async with sem:
                return await self.search_work(t)
        return await asyncio.gather(*[_search(t) for t in titles])

    def _build_search_url(self, title: str) -> str:
        # Use title.search filter for precise title matching
        # (the generic search= endpoint often returns unrelated high-citation papers)
        # Strip colons/special chars that break OpenAlex filter syntax
        import re as _re
        clean = _re.sub(r'[:\-,;\'\"()（）\[\]]', ' ', title)
        clean = ' '.join(clean.split())  # collapse whitespace
        return f"{BASE_URL}/works?filter=title.search:{quote(clean)}&per_page=1"

    def _parse_work(self, work: dict) -> dict:
        authors = []
        for authorship in work.get("authorships", []):
            author = authorship.get("author", {})
            institutions = authorship.get("institutions", [])
            inst = institutions[0] if institutions else {}
            authors.append({
                "name": author.get("display_name", ""),
                "openalex_id": author.get("id", ""),
                "affiliation": inst.get("display_name", ""),
                "country": inst.get("country_code", ""),
            })
        return {
            "title": work.get("title", ""),
            "year": work.get("publication_year"),
            "doi": work.get("doi", ""),
            "cited_by_count": work.get("cited_by_count", 0),
            "openalex_id": work.get("id", ""),
            "authors": authors,
            "source": "openalex",
        }

    def _parse_author(self, author: dict) -> dict:
        stats = author.get("summary_stats", {})
        affiliations = author.get("affiliations", [])
        current = affiliations[0] if affiliations else {}
        return {
            "name": author.get("display_name", ""),
            "openalex_id": author.get("id", ""),
            "h_index": stats.get("h_index", 0),
            "citation_count": author.get("cited_by_count", 0),
            "affiliation": current.get("institution", {}).get("display_name", ""),
            "source": "openalex",
        }

    async def close(self):
        await self._client.aclose()
