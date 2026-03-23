"""Shared HTTP client factory with proxy auto-detection.

Detects system HTTP proxy and configures httpx accordingly.
SOCKS5 proxies (common in China) are skipped since httpx doesn't
support them natively; only HTTP/HTTPS proxies are used.
"""
import os
import httpx
from typing import Optional


def _detect_http_proxy() -> Optional[str]:
    """Detect HTTP proxy from environment, skip SOCKS proxies."""
    for var in ["HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"]:
        proxy = os.environ.get(var, "")
        if proxy and proxy.startswith("http"):
            return proxy
    return None


def make_async_client(timeout: float = 30.0) -> httpx.AsyncClient:
    """Create an httpx AsyncClient with auto-detected proxy.

    Uses HTTP proxy if available, otherwise direct connection.
    """
    proxy = _detect_http_proxy()
    return httpx.AsyncClient(
        proxy=proxy,
        timeout=timeout,
        headers={"User-Agent": "CitationClaw/2.0 (academic research tool)"},
    )
