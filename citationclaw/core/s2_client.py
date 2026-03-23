"""Semantic Scholar API client for academic metadata.

API docs: https://api.semanticscholar.org/
Free tier: 1 req/s without key, higher with API key.
Unique fields: h_index, influentialCitationCount.
"""
import asyncio
from typing import Optional, List
from urllib.parse import quote

from citationclaw.core.http_utils import make_async_client

BASE_URL = "https://api.semanticscholar.org/graph/v1"

class S2Client:
    def __init__(self, api_key: Optional[str] = None):
        self._client = make_async_client(timeout=30.0)
        if api_key:
            self._client.headers["x-api-key"] = api_key
        self._rate_delay = 1.0  # 1 req/s for free tier

    async def search_paper(self, title: str) -> Optional[dict]:
        url = self._build_search_url(title)
        await asyncio.sleep(self._rate_delay)
        resp = await self._client.get(url)
        if resp.status_code != 200:
            return None
        data = resp.json()
        results = data.get("data", [])
        if not results:
            return None
        return self._parse_paper(results[0])

    async def get_author(self, author_id: str) -> Optional[dict]:
        url = f"{BASE_URL}/author/{author_id}?fields=name,hIndex,citationCount,affiliations"
        await asyncio.sleep(self._rate_delay)
        resp = await self._client.get(url)
        if resp.status_code != 200:
            return None
        return self._parse_author(resp.json())

    def _build_search_url(self, title: str) -> str:
        fields = "title,year,authors,citationCount,influentialCitationCount,externalIds,isOpenAccess,openAccessPdf"
        return f"{BASE_URL}/paper/search?query={quote(title)}&limit=1&fields={fields}"

    def _parse_paper(self, paper: dict) -> dict:
        authors = []
        for author in paper.get("authors", []):
            authors.append({
                "name": author.get("name", ""),
                "s2_id": author.get("authorId", ""),
            })
        ext_ids = paper.get("externalIds", {})
        pdf_info = paper.get("openAccessPdf") or {}
        return {
            "title": paper.get("title", ""),
            "year": paper.get("year"),
            "doi": ext_ids.get("DOI", ""),
            "cited_by_count": paper.get("citationCount", 0),
            "influential_citation_count": paper.get("influentialCitationCount", 0),
            "s2_id": paper.get("paperId", ""),
            "authors": authors,
            "pdf_url": pdf_info.get("url", ""),
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
