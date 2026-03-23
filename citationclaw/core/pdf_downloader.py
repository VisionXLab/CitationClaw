"""Multi-source PDF downloader with local caching.

Sources (in priority order):
1. arXiv direct link (free, reliable)
2. Semantic Scholar PDF link
3. Unpaywall API (free, requires email)
4. DOI redirect (follow DOI -> publisher -> PDF link)
"""
import hashlib
import asyncio
from pathlib import Path
from typing import Optional, List

from citationclaw.core.http_utils import make_async_client

DEFAULT_CACHE_DIR = Path("data/cache/pdf_cache")


class PDFDownloader:
    def __init__(self, cache_dir: Optional[Path] = None, email: Optional[str] = None):
        self._cache_dir = cache_dir or DEFAULT_CACHE_DIR
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._email = email or "citationclaw@research.tool"
        self._client = make_async_client(timeout=60.0)
        self._client.follow_redirects = True

    def _cache_path(self, paper: dict) -> Path:
        key = (paper.get("doi") or paper.get("Paper_Title")
               or paper.get("title") or "unknown")
        h = hashlib.md5(key.encode()).hexdigest()
        return self._cache_dir / f"{h}.pdf"

    async def download(self, paper: dict, log=None) -> Optional[Path]:
        """Try multiple sources to download PDF. Returns cached path or None."""
        title = paper.get("Paper_Title", paper.get("title", "?"))[:40]
        cached = self._cache_path(paper)
        if cached.exists() and cached.stat().st_size > 0:
            if log:
                log(f"    [PDF缓存] {title}")
            return cached

        sources = self._determine_sources(paper)
        if not sources:
            if log:
                log(f"    [PDF] 无可用来源 (无pdf_url, 无doi): {title}")
            return None

        for source in sources:
            try:
                pdf_bytes = await source["fn"](paper)
                if pdf_bytes and len(pdf_bytes) > 1000:  # Sanity check
                    cached.write_bytes(pdf_bytes)
                    if log:
                        log(f"    [PDF✓] {source['name']}下载成功 ({len(pdf_bytes)//1024}KB): {title}")
                    return cached
            except Exception as e:
                if log:
                    log(f"    [PDF✗] {source['name']}失败: {e}")
                continue
        if log:
            log(f"    [PDF] 所有来源均失败: {title}")
        return None

    async def batch_download(self, papers: List[dict], concurrency: int = 10) -> List[Optional[Path]]:
        sem = asyncio.Semaphore(concurrency)
        async def _dl(p):
            async with sem:
                return await self.download(p)
        return await asyncio.gather(*[_dl(p) for p in papers])

    def _determine_sources(self, paper: dict) -> List[dict]:
        """Return download sources in priority order based on available metadata."""
        sources = []
        # 1. arXiv direct (if we have arxiv PDF url)
        if paper.get("pdf_url") and "arxiv.org" in paper.get("pdf_url", ""):
            sources.append({"name": "arxiv", "fn": self._try_direct_url})
        # 2. Any other direct PDF url (e.g. from S2)
        elif paper.get("pdf_url"):
            sources.append({"name": "direct", "fn": self._try_direct_url})
        # 3. Unpaywall (if DOI available)
        if paper.get("doi"):
            sources.append({"name": "unpaywall", "fn": self._try_unpaywall})
        # 4. DOI redirect
        if paper.get("doi"):
            sources.append({"name": "doi", "fn": self._try_doi_redirect})
        return sources

    async def _try_direct_url(self, paper: dict) -> Optional[bytes]:
        url = paper.get("pdf_url", "")
        if not url:
            return None
        resp = await self._client.get(url)
        if resp.status_code == 200 and b"%PDF" in resp.content[:10]:
            return resp.content
        return None

    async def _try_unpaywall(self, paper: dict) -> Optional[bytes]:
        doi = paper.get("doi", "")
        if not doi:
            return None
        url = f"https://api.unpaywall.org/v2/{doi}?email={self._email}"
        resp = await self._client.get(url)
        if resp.status_code != 200:
            return None
        data = resp.json()
        best_oa = data.get("best_oa_location") or {}
        pdf_url = best_oa.get("url_for_pdf", "")
        if not pdf_url:
            return None
        pdf_resp = await self._client.get(pdf_url)
        if pdf_resp.status_code == 200 and b"%PDF" in pdf_resp.content[:10]:
            return pdf_resp.content
        return None

    async def _try_doi_redirect(self, paper: dict) -> Optional[bytes]:
        doi = paper.get("doi", "")
        if not doi:
            return None
        url = f"https://doi.org/{doi}"
        try:
            resp = await self._client.get(url)
            if resp.status_code == 200 and b"%PDF" in resp.content[:10]:
                return resp.content
        except Exception:
            pass
        return None

    async def close(self):
        await self._client.aclose()
