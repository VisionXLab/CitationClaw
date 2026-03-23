"""Playwright browser manager with proxy detection and tab pool.

Manages browser lifecycle for scholar search operations.
Playwright is lazily imported — code works without it for testing.
"""
import os
import asyncio
from typing import Optional, Dict
from urllib.parse import quote

try:
    from playwright.async_api import async_playwright, Browser, Page
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


def detect_system_proxy() -> Optional[Dict[str, str]]:
    """Detect system proxy from environment variables."""
    for var in ["HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy"]:
        proxy = os.environ.get(var)
        if proxy:
            return {"server": proxy}
    return None


class BrowserManager:
    """Manage Playwright browser lifecycle and tab pool."""

    def __init__(self, headless: bool = True, proxy: Optional[str] = None):
        self._headless = headless
        self._proxy_config = proxy
        self._browser: Optional[object] = None
        self._playwright = None
        self._sem: Optional[asyncio.Semaphore] = None

    async def init(self, max_tabs: int = 5):
        """Launch browser with proxy detection/configuration."""
        if not HAS_PLAYWRIGHT:
            raise RuntimeError("Playwright is not installed. Run: pip install playwright && playwright install chromium")

        self._sem = asyncio.Semaphore(max_tabs)
        self._playwright = await async_playwright().start()

        launch_args = {"headless": self._headless}

        # Configure proxy
        if self._proxy_config == "direct":
            pass  # No proxy
        elif self._proxy_config and self._proxy_config != "auto":
            launch_args["proxy"] = {"server": self._proxy_config}
        else:
            # Auto-detect
            system_proxy = detect_system_proxy()
            if system_proxy:
                launch_args["proxy"] = system_proxy

        self._browser = await self._playwright.chromium.launch(**launch_args)

    async def search_google(self, query: str) -> str:
        """Search Google, return result page text."""
        if not self._browser:
            raise RuntimeError("Browser not initialized. Call init() first.")

        async with self._sem:
            page = await self._browser.new_page()
            try:
                url = self._build_google_url(query)
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                await page.wait_for_timeout(2000)  # Wait for dynamic content
                text = await page.evaluate("() => document.body.innerText")
                return text or ""
            finally:
                await page.close()

    async def get_page_text(self, url: str) -> str:
        """Navigate to URL, return visible text content."""
        if not self._browser:
            raise RuntimeError("Browser not initialized. Call init() first.")

        async with self._sem:
            page = await self._browser.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                await page.wait_for_timeout(1000)
                text = await page.evaluate("() => document.body.innerText")
                return text or ""
            finally:
                await page.close()

    def _build_google_url(self, query: str) -> str:
        return f"https://www.google.com/search?q={quote(query)}"

    async def close(self):
        """Close browser and all tabs."""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
