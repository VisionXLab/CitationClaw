"""Smart multi-source PDF downloader — fused from PaperRadar + CitationClaw.

Core logic ported from PaperRadar's smart_download_pdf (proven high success rate).
Added: GS sidebar PDF link, GS "all versions" scraping, MinerU Cloud parse cache.
Added: CDP browser session download for IEEE, Elsevier, and ACM.

Download priority (tried in order):
  0. Cache (instant)
  1. GS sidebar PDF link (direct from Google Scholar)
  2. OpenAlex OA PDF
  3. CVF open access (CVPR/ICCV/WACV direct URL construction)
  4. openAccessPdf / S2 direct (non-arxiv, non-doi)
  5. S2 API lookup (openAccessPdf)
  6. DBLP conference lookup (NeurIPS/ICML/ICLR/AAAI)
  7. Sci-Hub (3 mirrors)
  8. arXiv PDF
  9. GS paper_link + smart transform (CVF/OpenReview/MDPI/IEEE/Springer/ACL)
 10. Publisher page + curl + SOCKS5 + Chrome Cookie
 11. DOI redirect + Unpaywall
 12. CDP browser session — IEEE (requires debug browser with auth)
 13. CDP browser session — Elsevier/ScienceDirect (requires debug browser with auth)
 14. CDP browser session — ACM Digital Library (requires debug browser with auth)
"""
import hashlib
import json
import random
import re
import os
import sys
import asyncio
import base64
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from http.client import RemoteDisconnected
from urllib.parse import urlparse, quote
from urllib.request import Request, urlopen

import subprocess
DEFAULT_CACHE_DIR = Path("data/cache/pdf_cache")

_ARXIV_ID_RE_LOCAL = re.compile(r'^(\d{4})\.(\d{4,5})(v\d+)?$')


def _is_valid_arxiv_id_local(arxiv_id: str) -> bool:
    """Accept only YYMM.NNNNN[vN] where YYMM is past or current month.

    Duplicate of metadata_collector._is_valid_arxiv_id to avoid circular import.
    """
    if not arxiv_id:
        return False
    m = _ARXIV_ID_RE_LOCAL.match(arxiv_id.strip())
    if not m:
        return False
    yy, mm = int(m.group(1)[:2]), int(m.group(1)[2:])
    if not (1 <= mm <= 12):
        return False
    now = datetime.utcnow()
    paper_ym = (2000 + yy) * 12 + (mm - 1)
    today_ym = now.year * 12 + (now.month - 1)
    return paper_ym <= today_ym

# Sci-Hub mirrors
SCIHUB_MIRRORS = [
    "https://sci-hub.se",
    "https://sci-hub.st",
    "https://sci-hub.ru",
]

# Publisher domains that may need Chrome cookies
_PUBLISHER_DOMAINS = [
    "ieeexplore.ieee.org",
    "dl.acm.org",
    "link.springer.com",
    "www.sciencedirect.com",
    "onlinelibrary.wiley.com",
]

# Friendly source labels for logging
_SOURCE_LABELS = {
    "gs_pdf": "GS侧栏PDF",
    "cvf": "CVF开放获取",
    "openaccess": "S2开放获取",
    "s2_page": "S2页面PDF",
    "dblp": "DBLP会议版",
    "scihub": "Sci-Hub",
    "arxiv": "arXiv",
    "gs_link": "GS论文链接",
    "publisher": "出版商+Cookie",
    "doi": "DOI跳转",
    "gs_versions": "GS版本页",
    "oa_pdf": "OpenAlex开放获取",
    "unpaywall": "Unpaywall",
}

# ── Proxy detection (same as PaperRadar: skip socks, use HTTP) ─────────
_HTTP_PROXY = None
for _var in ["HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"]:
    _val = os.environ.get(_var, "")
    if _val and _val.startswith("http"):
        _HTTP_PROXY = _val
        break


# ── Chrome cookie injection ────────────────────────────────────────────
_cookie_cache: dict = {}


# Auto-detect Chrome profile with most cookies (= institution login profile)
_chrome_profile_path: Optional[str] = None


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _iter_browser_cookie_files() -> List[str]:
    """Return candidate Chromium cookie DB paths for the current platform."""
    roots: List[Path] = []
    home = Path.home()

    if sys.platform == "win32":
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        if local_appdata:
            roots.extend([
                Path(local_appdata) / "Google/Chrome/User Data",
                Path(local_appdata) / "Microsoft/Edge/User Data",
            ])
        roots.append(_project_root() / "runtime" / "debug_browser_profile")
    elif sys.platform == "darwin":
        roots.extend([
            home / "Library/Application Support/Google/Chrome",
            home / "Library/Application Support/Microsoft Edge",
        ])
    else:
        roots.extend([
            home / ".config/google-chrome",
            home / ".config/chromium",
            home / ".config/microsoft-edge",
        ])

    patterns = [
        "Default/Network/Cookies",
        "Profile */Network/Cookies",
        "Guest Profile/Network/Cookies",
        "Default/Cookies",
        "Profile */Cookies",
        "Guest Profile/Cookies",
        "Network/Cookies",
        "Cookies",
    ]

    seen: set[str] = set()
    files: List[str] = []
    for root in roots:
        if not root.exists():
            continue
        for pattern in patterns:
            for path in root.glob(pattern):
                if not path.is_file():
                    continue
                resolved = str(path.resolve())
                if resolved in seen:
                    continue
                seen.add(resolved)
                files.append(resolved)
    return files


def _detect_chrome_profile() -> str:
    """Find the Chromium profile cookie DB with the most IEEE cookies."""
    global _chrome_profile_path
    if _chrome_profile_path is not None:
        return _chrome_profile_path

    try:
        from pycookiecheat import chrome_cookies
    except Exception:
        _chrome_profile_path = ""
        return ""

    best = ""
    best_n = 0
    for cp in _iter_browser_cookie_files():
        try:
            n = len(chrome_cookies("https://ieeexplore.ieee.org", cookie_file=cp))
            if n > best_n:
                best_n = n
                best = cp
        except Exception:
            pass
    _chrome_profile_path = best
    return best


def _get_cookies_for_url(url: str) -> dict:
    """Get Chrome cookies for publisher domains from the best profile."""
    try:
        host = urlparse(url).netloc
        for domain in _PUBLISHER_DOMAINS:
            if domain in host:
                if domain in _cookie_cache:
                    return _cookie_cache[domain]
                from pycookiecheat import chrome_cookies
                profile = _detect_chrome_profile()
                if profile:
                    cookies = chrome_cookies(f"https://{domain}", cookie_file=profile)
                else:
                    cookies = chrome_cookies(f"https://{domain}")
                _cookie_cache[domain] = cookies
                return cookies
    except Exception:
        pass
    return {}


# SOCKS5 proxy for curl (httpx doesn't support socks5h)
_SOCKS_PROXY = os.environ.get("ALL_PROXY") or os.environ.get("all_proxy") or ""
if not _SOCKS_PROXY.startswith("socks"):
    _SOCKS_PROXY = ""


# ── HTML PDF extraction (covers IEEE JSON pdfUrl, meta tags, etc.) ─────
def _extract_pdf_url_from_html(html: str, base_url: str) -> Optional[str]:
    """Extract PDF URL from HTML page (publisher landing pages)."""
    parsed_base = urlparse(base_url)
    base_origin = f"{parsed_base.scheme}://{parsed_base.netloc}"

    def _abs(url):
        if url.startswith("//"):
            return f"https:{url}"
        if url.startswith("/"):
            return f"{base_origin}{url}"
        return url

    # 1. citation_pdf_url meta tag (IEEE, ACM, Google Scholar standard)
    m = re.search(r'<meta\s+name=["\']citation_pdf_url["\']\s+content=["\'](.*?)["\']', html, re.I)
    if m:
        return _abs(m.group(1))

    # 2. IEEE pdfUrl/stampUrl in embedded JSON
    for pat in [r'"pdfUrl"\s*:\s*"(.*?)"', r'"stampUrl"\s*:\s*"(.*?)"']:
        m = re.search(pat, html)
        if m:
            return _abs(m.group(1))

    # 3. Direct PDF link patterns
    for pat in [
        r'href=["\'](https?://[^"\']*?\.pdf[^"\']*)["\']',
        r'href=["\']([^"\']*?/pdf/[^"\']*)["\']',
        r'href=["\']([^"\']*?download[^"\']*?\.pdf[^"\']*)["\']',
    ]:
        m = re.search(pat, html, re.I)
        if m:
            return _abs(m.group(1))

    # 4. iframe/embed src
    for pat in [
        r'<embed[^>]+src=["\'](.*?\.pdf[^"\']*)["\']',
        r'<iframe[^>]+src=["\'](.*?\.pdf[^"\']*)["\']',
    ]:
        m = re.search(pat, html, re.I)
        if m:
            return _abs(m.group(1))

    return None


def _extract_scihub_pdf_url(html: str, base_url: str) -> Optional[str]:
    """Extract PDF URL from Sci-Hub HTML page."""
    for pat in [
        r'<meta\s+name=["\']citation_pdf_url["\']\s+content=["\'](.*?)["\']',
        r'href=["\'](/storage/[^"\']+\.pdf[^"\']*)["\']',
        r'content=["\'](/storage/[^"\']+\.pdf[^"\']*)["\']',
        r'<embed[^>]+src=["\'](.*?\.pdf[^"\']*)["\']',
        r'<iframe[^>]+src=["\'](.*?\.pdf[^"\']*)["\']',
        r'<embed[^>]+src=["\']([^"\']+)["\']',
        r'<iframe[^>]+src=["\']([^"\']+)["\']',
        r'location\.href\s*=\s*["\']([^"\']+\.pdf[^"\']*)["\']',
    ]:
        m = re.search(pat, html, re.I)
        if m:
            url = m.group(1)
            if url.startswith("//"):
                url = "https:" + url
            elif url.startswith("/"):
                parsed = urlparse(base_url)
                url = f"{parsed.scheme}://{parsed.netloc}{url}"
            return url
    return None


# ── URL transform (paper page → direct PDF) ───────────────────────────
def _transform_url(url: str) -> str:
    """Transform known paper page URLs to direct PDF URLs."""
    # CVF open access
    if "openaccess.thecvf.com" in url and "/html/" in url and url.endswith(".html"):
        return url.replace("/html/", "/papers/").replace("_paper.html", "_paper.pdf")
    # OpenReview
    if "openreview.net/forum" in url:
        return url.replace("/forum?", "/pdf?")
    # ACL Anthology
    if "aclanthology.org" in url:
        if "/abs/" in url:
            return url.replace("/abs/", "/pdf/")
        if not url.endswith(".pdf"):
            return url.rstrip("/") + ".pdf"
    # arXiv
    if "arxiv.org/abs/" in url:
        return url.replace("/abs/", "/pdf/")
    # MDPI
    if "mdpi.com" in url:
        if "/htm" in url:
            return url.replace("/htm", "/pdf")
        if re.match(r'https?://www\.mdpi\.com/[\d-]+/\d+/\d+/\d+$', url):
            return url.rstrip("/") + "/pdf"
    # Springer: /article/DOI → /content/pdf/DOI.pdf
    if "link.springer.com" in url and "/article/" in url:
        m = re.search(r'/article/(10\.\d+/[^\s?#]+)', url)
        if m:
            doi = m.group(1).rstrip('/')
            return f"https://link.springer.com/content/pdf/{doi}.pdf"
    # IEEE abstract → stamp
    if "ieeexplore.ieee.org" in url and "/abstract/" in url:
        m = re.search(r'/document/(\d+)', url)
        if m:
            return f"https://ieeexplore.ieee.org/stamp/stamp.jsp?arnumber={m.group(1)}"
    # ScienceDirect: /pii/XXX → /pii/XXX/pdfft with download params
    if "sciencedirect.com" in url and "/pii/" in url and "/pdfft" not in url:
        return url.rstrip("/") + "/pdfft?isDTMRedir=true&download=true"
    # NeurIPS proceedings
    if "papers.nips.cc" in url or "proceedings.neurips.cc" in url:
        if "-Abstract" in url:
            return url.replace("-Abstract-Conference.html", "-Paper-Conference.pdf").replace("-Abstract.html", "-Paper.pdf")
    # PMLR (ICML, AISTATS)
    if "proceedings.mlr.press" in url and url.endswith(".html"):
        base = url[:-5]
        slug = base.rsplit("/", 1)[-1]
        return f"{base}/{slug}.pdf"
    # AAAI
    if "ojs.aaai.org" in url and "/article/view/" in url:
        return url
    return url


def _build_cvf_candidates(doi: str, venue: str, year, title: str, first_author: str) -> list:
    """Build CVF open-access PDF URL candidates (CVPR/ICCV/WACV)."""
    if not title:
        return []
    venue_lower = (venue or "").lower()
    doi_lower = (doi or "").lower()
    conf = None
    if "cvpr" in venue_lower or "cvpr" in doi_lower:
        conf = "CVPR"
    elif "iccv" in venue_lower or "iccv" in doi_lower:
        conf = "ICCV"
    elif "wacv" in venue_lower or "wacv" in doi_lower:
        conf = "WACV"
    if not conf or not year:
        return []
    safe_title = re.sub(r'[^a-zA-Z0-9\s\-]', '', title)
    safe_title = re.sub(r'\s+', '_', safe_title.strip())
    safe_author = re.sub(r'[^a-zA-Z]', '', first_author or "Unknown")
    base = "https://openaccess.thecvf.com"
    return [f"{base}/content/{conf}{year}/papers/{safe_author}_{safe_title}_{conf}_{year}_paper.pdf"]


def _paper_title(paper: dict) -> str:
    return paper.get("Paper_Title") or paper.get("paper_title") or paper.get("title") or ""


def _paper_link(paper: dict) -> str:
    return paper.get("paper_link") or paper.get("Paper_Link") or ""


def _paper_year(paper: dict):
    return paper.get("paper_year") or paper.get("Paper_Year") or paper.get("year") or 0


def _paper_venue(paper: dict) -> str:
    return paper.get("venue") or paper.get("Venue") or ""


def _paper_pdf_url(paper: dict) -> str:
    return paper.get("pdf_url") or paper.get("PDF_URL") or ""


def _paper_oa_pdf_url(paper: dict) -> str:
    return paper.get("oa_pdf_url") or paper.get("oaPdfUrl") or ""


def _paper_gs_pdf_link(paper: dict) -> str:
    return paper.get("gs_pdf_link") or paper.get("GS_PDF_Link") or ""


# ── CDP (Chrome DevTools Protocol) helpers ────────────────────────────
# Used by steps 13-14 to download PDFs via a live, authenticated browser session.
# Requires: websocket-client (pip install websocket-client) + browser with --remote-debugging-port.

try:
    import websocket as _websocket_mod
except ImportError:
    _websocket_mod = None

# ScienceDirect pdfDownload metadata regex
_SD_PDF_DOWNLOAD_RE = re.compile(
    r'"pdfDownload":\{"isPdfFullText":(?:true|false),"urlMetadata":\{"queryParams":\{"md5":"([^"]+)","pid":"([^"]+)"\},"pii":"([^"]+)","pdfExtension":"([^"]+)","path":"([^"]+)"\}\}'
)


def _cdp_available() -> bool:
    return _websocket_mod is not None


_cdp_last_launch_ts = 0.0


def _cdp_ensure_browser(debug_port: int) -> bool:
    """Ensure a debug browser is running. Auto-launch if needed."""
    global _cdp_last_launch_ts
    if not _cdp_available():
        return False
    if _cdp_check_connection(debug_port):
        return True

    # Give an already-launching browser a short chance to come up.
    for _ in range(3):
        import time as _t
        _t.sleep(1)
        if _cdp_check_connection(debug_port):
            return True

    # Avoid hammering duplicate launches while still allowing recovery
    # if the debug browser exits during a long batch run.
    now = time.time()
    if now - _cdp_last_launch_ts < 5:
        return False

    # Auto-launch Edge or Chrome with remote debugging
    _cdp_last_launch_ts = now
    browser_paths = [
        "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
        "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
        "C:/Program Files/Google/Chrome/Application/chrome.exe",
        "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    ]
    binary = None
    for p in browser_paths:
        if Path(p).exists():
            binary = p
            break
    if not binary:
        return False

    profile_dir = Path("runtime/debug_browser_profile")
    profile_dir.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.Popen([
            binary,
            f"--remote-debugging-port={debug_port}",
            f"--user-data-dir={profile_dir.resolve()}",
            "--profile-directory=Default",
            "--new-window", "about:blank",
        ])
    except Exception:
        return False

    # Wait for browser to start (up to 10s)
    for _ in range(10):
        import time as _t
        _t.sleep(1)
        if _cdp_check_connection(debug_port):
            return True
    return False


def _cdp_check_connection(debug_port: int, timeout: int = 3) -> bool:
    try:
        data = _cdp_urlopen_json(f"http://127.0.0.1:{debug_port}/json/version", timeout=timeout, retries=1)
        return "Browser" in data or "webSocketDebuggerUrl" in data
    except Exception:
        return False


def _cdp_urlopen_json(url: str, timeout: int = 10, method: Optional[str] = None,
                      retries: int = 2, retry_delay: float = 1.0):
    last_exc = None
    for attempt in range(retries + 1):
        try:
            req = Request(url, method=method) if method else Request(url)
            with urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode()
            return json.loads(raw)
        except (RemoteDisconnected, ConnectionResetError, TimeoutError, OSError) as e:
            last_exc = e
            if attempt >= retries:
                raise
            time.sleep(retry_delay)
    if last_exc:
        raise last_exc


def _cdp_list_tabs(debug_port: int) -> list:
    try:
        return _cdp_urlopen_json(f"http://127.0.0.1:{debug_port}/json/list", timeout=10, retries=2)
    except Exception:
        return []


def _cdp_open_page(debug_port: int, url: str) -> dict:
    return _cdp_urlopen_json(
        f"http://127.0.0.1:{debug_port}/json/new?{quote(url, safe=':/?&=%')}",
        timeout=20,
        method="PUT",
        retries=2,
    )


def _cdp_close_page(debug_port: int, page_id: str):
    try:
        _cdp_urlopen_json(f"http://127.0.0.1:{debug_port}/json/close/{page_id}", timeout=5, retries=1)
    except Exception:
        pass


def _cdp_find_tab(debug_port: int, host_substring: str,
                  preferred_markers: Optional[List[str]] = None,
                  excluded_markers: Optional[List[str]] = None) -> Optional[dict]:
    preferred_markers = preferred_markers or []
    excluded_markers = excluded_markers or []
    tabs = _cdp_list_tabs(debug_port)

    candidates = []
    for t in tabs:
        if t.get("type") != "page":
            continue
        url = t.get("url", "")
        url_lower = url.lower()
        if host_substring not in url_lower:
            continue
        if any(marker in url_lower for marker in excluded_markers):
            continue
        candidates.append(t)

    for marker in preferred_markers:
        for t in candidates:
            if marker in t.get("url", "").lower():
                return t
    return candidates[0] if candidates else None


def _cdp_call(ws_url: str, method: str, params: dict = None, msg_id: int = 1, timeout: int = 180) -> dict:
    ws = _websocket_mod.create_connection(ws_url, timeout=timeout, suppress_origin=True)
    try:
        ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == msg_id:
                return msg
    finally:
        ws.close()


def _cdp_evaluate(ws_url: str, expression: str, await_promise: bool = False, msg_id: int = 1):
    msg = _cdp_call(ws_url, "Runtime.evaluate", {
        "expression": expression, "returnByValue": True, "awaitPromise": await_promise,
    }, msg_id=msg_id)
    return msg.get("result", {}).get("result", {}).get("value")


def _cdp_fetch_pdf_in_context(ws_url: str, pdf_url: str, log=None) -> Optional[bytes]:
    """Execute fetch() in a page context to download a PDF. Returns bytes or None."""
    _log = log or (lambda msg: None)
    _cdp_evaluate(ws_url, f'window.__pdfUrl = {json.dumps(pdf_url)};', msg_id=40)
    js = '''
fetch(window.__pdfUrl, {credentials: "include"})
  .then(r => { if (!r.ok) return "ERR:HTTP_" + r.status; return r.arrayBuffer(); })
  .then(buf => {
    if (typeof buf === "string") return buf;
    const bytes = new Uint8Array(buf);
    const chunk = 0x8000;
    let binary = "";
    for (let i = 0; i < bytes.length; i += chunk) {
      binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
    }
    return btoa(binary);
  })
  .catch(e => "ERR:" + e.message)
'''
    try:
        value = _cdp_evaluate(ws_url, js.strip(), await_promise=True, msg_id=50)
        if not value:
            _log("  [CDP] fetch() returned nothing")
            return None
        if isinstance(value, str) and value.startswith("ERR:"):
            _log(f"  [CDP] fetch() failed: {value}")
            return None
        data = base64.b64decode(value)
        if data[:5] == b"%PDF-":
            _log(f"  [CDP] fetch success ({len(data)//1024}KB)")
            return data
        _log(f"  [CDP] non-PDF response ({len(data)} bytes, header={data[:30]})")
        return None
    except Exception as e:
        _log(f"  [CDP] fetch error: {type(e).__name__}: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════
class PDFDownloader:
    """Smart multi-source PDF downloader with caching."""

    # Class-level lock: CDP operations must be serialized (one browser, shared tabs)
    _cdp_lock = asyncio.Lock()

    def __init__(self, cache_dir: Optional[Path] = None, email: Optional[str] = None,
                 cdp_debug_port: int = 0):
        self._cache_dir = cache_dir or DEFAULT_CACHE_DIR
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._email = email or "citationclaw@research.tool"
        self._cdp_debug_port = cdp_debug_port

    @staticmethod
    def _make_client(timeout: float = 30.0):
        """Create httpx client with HTTP proxy (skip socks5h). Ported from PaperRadar."""
        import httpx
        return httpx.AsyncClient(
            follow_redirects=True, timeout=timeout, trust_env=False,
            proxy=_HTTP_PROXY,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
            },
        )

    def _cache_path(self, paper: dict) -> Path:
        key = paper.get("doi") or _paper_title(paper) or "unknown"
        h = hashlib.md5(key.encode()).hexdigest()
        return self._cache_dir / f"{h}.pdf"

    def _ensure_cdp_ready(self, source: str, log=None) -> bool:
        """Ensure the configured debug browser is reachable before CDP download."""
        if not self._cdp_debug_port:
            if log:
                log(f"  [{source}] skipped: cdp_debug_port is not configured")
            return False
        if _cdp_check_connection(self._cdp_debug_port):
            return True
        if log:
            log(f"  [{source}] port {self._cdp_debug_port} unreachable, trying to launch debug browser...")
        if _cdp_ensure_browser(self._cdp_debug_port):
            return True
        if log:
            log(
                f"  [{source}] debug browser unavailable on port {self._cdp_debug_port}; "
                f"run scripts/launch_edge_debug.ps1 and sign in first"
            )
        return False

    # ── Shared rate limiter for arxiv.org (3 concurrent, global across batch) ──
    _arxiv_sem = asyncio.Semaphore(3)

    # ── Structured failure recording ─────────────────────────────────
    @staticmethod
    def _record_failure(paper: dict, stage: str, **fields):
        """Append a structured failure entry to paper['_pdf_failures'].

        Used by retry/diagnostics layers to distinguish transient vs permanent
        errors. Fields commonly include: http_status, error_type, reason,
        detail (truncated). Silent no-op if paper is None.
        """
        if paper is None:
            return
        entry = {"stage": stage}
        for k, v in fields.items():
            if v is None or v == "":
                continue
            if isinstance(v, str) and len(v) > 120:
                v = v[:120]
            entry[k] = v
        paper.setdefault("_pdf_failures", []).append(entry)

    # ── Retry wrapper: transient network / 429 / timeouts ─────────────
    async def _try_url_with_retry(
        self,
        client,
        url: str,
        cookies: dict = None,
        attempts: int = 3,
        base_delay: float = 1.0,
        *,
        paper: dict = None,
        stage: str = None,
    ) -> Optional[bytes]:
        """Wrap _try_url with exponential backoff + jitter for transient errors."""
        for i in range(attempts):
            data = await self._try_url(client, url, cookies, paper=paper, stage=stage)
            if data:
                return data
            if i < attempts - 1:
                await asyncio.sleep(base_delay * (2 ** i) + random.uniform(0, 0.5))
        return None

    # ── Core: try downloading a single URL ────────────────────────────
    async def _try_url(self, client, url: str, cookies: dict = None,
                       *, paper: dict = None, stage: str = None) -> Optional[bytes]:
        """Try downloading from a URL, handling HTML pages with PDF extraction.

        If `paper` and `stage` are provided, records structured failure info
        (HTTP status, exception type) into `paper['_pdf_failures']`.
        """
        try:
            resp = await client.get(url, cookies=cookies or {})
            if resp.status_code != 200:
                PDFDownloader._record_failure(paper, stage or "try_url",
                                              http_status=resp.status_code,
                                              url=url)
                return None
            if resp.content[:5] == b"%PDF-":
                return resp.content
            # HTML page → try extracting real PDF link
            if len(resp.content) > 100:
                pdf_url = _extract_pdf_url_from_html(resp.text, str(resp.url))
                if pdf_url:
                    cookies2 = _get_cookies_for_url(pdf_url)
                    resp2 = await client.get(pdf_url, cookies=cookies2)
                    if resp2.status_code == 200 and resp2.content[:5] == b"%PDF-":
                        return resp2.content
                    # IEEE stamp returns another HTML → extract again
                    if resp2.status_code == 200 and resp2.content[:5] != b"%PDF-":
                        inner = _extract_pdf_url_from_html(resp2.text, str(resp2.url))
                        if inner:
                            resp3 = await client.get(inner, cookies=cookies2)
                            if resp3.status_code == 200 and resp3.content[:5] == b"%PDF-":
                                return resp3.content
                    PDFDownloader._record_failure(paper, stage or "try_url",
                                                  http_status=resp2.status_code,
                                                  reason="html_not_pdf", url=pdf_url)
                else:
                    PDFDownloader._record_failure(paper, stage or "try_url",
                                                  reason="no_pdf_link_in_html",
                                                  url=url)
            else:
                PDFDownloader._record_failure(paper, stage or "try_url",
                                              reason="empty_response", url=url)
        except Exception as e:
            PDFDownloader._record_failure(paper, stage or "try_url",
                                          error_type=type(e).__name__,
                                          detail=str(e), url=url)
        return None

    # ── curl-based publisher download (socks5h + Chrome cookies) ────────
    async def _curl_publisher_download(self, url: str) -> Optional[bytes]:
        """Download from publisher using curl with socks5h proxy + Chrome cookies.

        This bypasses httpx's socks5 limitation and Cloudflare bot detection.
        Only used for publisher domains (IEEE/Springer/ScienceDirect/ACM).
        """
        if not _SOCKS_PROXY:
            return None  # No socks proxy configured

        host = urlparse(url).netloc
        if not any(d in host for d in _PUBLISHER_DOMAINS):
            return None  # Not a publisher domain

        cookies = _get_cookies_for_url(url)
        if not cookies:
            return None

        cookie_str = '; '.join(f'{k}={v}' for k, v in cookies.items())

        def _curl(u):
            try:
                r = subprocess.run([
                    'curl', '-x', _SOCKS_PROXY, '-s', '-L',
                    '-H', 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    '-H', 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8',
                    '-H', 'Accept-Language: en-US,en;q=0.9',
                    '-b', cookie_str,
                    u
                ], capture_output=True, timeout=30)
                return r.stdout
            except Exception:
                return None

        try:
            # Step 1: Get publisher page
            data = await asyncio.to_thread(_curl, url)
            if not data or len(data) < 500:
                return None
            if data[:5] == b"%PDF-":
                return data

            # Step 2: Extract PDF URL from HTML
            html = data.decode('utf-8', errors='ignore')
            pdf_url = _extract_pdf_url_from_html(html, url)
            if not pdf_url:
                return None

            # Step 3: Download from extracted URL
            data2 = await asyncio.to_thread(_curl, pdf_url)
            if data2 and data2[:5] == b"%PDF-":
                return data2

            # Step 4: If stamp page, extract inner URL (IEEE getPDF.jsp)
            if data2 and len(data2) > 200 and data2[:5] != b"%PDF-":
                import re as _re
                inner_html = data2.decode('utf-8', errors='ignore')
                for pat in [r'src="(https?://[^"]*getPDF[^"]*?)"',
                            r'src="(https?://[^"]*\.pdf[^"]*?)"',
                            r'"(https?://[^"]*iel[^"]*\.pdf[^"]*?)"']:
                    m = _re.search(pat, inner_html)
                    if m:
                        data3 = await asyncio.to_thread(_curl, m.group(1))
                        if data3 and data3[:5] == b"%PDF-":
                            return data3
        except Exception:
            pass
        return None

    @staticmethod
    def _publisher_label(url: str) -> str:
        """Generate a descriptive label for publisher-based download."""
        host = urlparse(url).netloc.lower()
        if "ieee" in host:
            return "IEEE+Cookie"
        if "springer" in host:
            return "Springer+Cookie"
        if "sciencedirect" in host:
            return "ScienceDirect+Cookie"
        if "acm" in host:
            return "ACM+Cookie"
        if "wiley" in host:
            return "Wiley+Cookie"
        if "doi.org" in host:
            return "DOI+Cookie"
        return "出版商+Cookie"


    # ── Main download method (PaperRadar-style smart download) ────────
    async def download(self, paper: dict, log=None) -> Optional[Path]:
        """Smart multi-source PDF download. Returns cached path or None."""
        title = (_paper_title(paper) or "?")[:40]
        # Fresh failure log for this paper (observability; consumed by
        # task_executor / pipeline_adapter to surface in xlsx)
        paper["_pdf_failures"] = []
        cached = self._cache_path(paper)
        if cached.exists() and cached.stat().st_size > 0:
            src_file = cached.with_suffix(".pdf.src")
            if src_file.exists():
                try:
                    paper["_pdf_source"] = src_file.read_text(encoding="utf-8").strip() or "cache"
                except Exception:
                    paper["_pdf_source"] = "cache"
            else:
                paper["_pdf_source"] = "cache"
            if log:
                log(f"[PDF] 缓存命中: {title}")
            return cached

        doi = (paper.get("doi") or "").replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
        pdf_url = _paper_pdf_url(paper)
        oa_pdf_url = _paper_oa_pdf_url(paper)
        # ArXiv ID: from metadata (Phase 2) or extracted from pdf_url
        arxiv_id = paper.get("arxiv_id") or ""
        if arxiv_id and not _is_valid_arxiv_id_local(arxiv_id):
            arxiv_id = ""  # drop invalid / future-dated IDs from upstream
        if not arxiv_id and pdf_url and "arxiv.org" in pdf_url:
            m = re.search(r'arxiv\.org/(?:abs|pdf)/(\d+\.\d+)', pdf_url)
            if m and _is_valid_arxiv_id_local(m.group(1)):
                arxiv_id = m.group(1)
        paper_link = _paper_link(paper)
        gs_pdf_link = _paper_gs_pdf_link(paper)
        s2_id = paper.get("s2_id") or ""
        venue = _paper_venue(paper)
        year = _paper_year(paper)
        full_title = _paper_title(paper)

        # Ordered download attempts
        attempts = []

        def _ok(data: Optional[bytes], source: str) -> bool:
            """Check if download succeeded, save to cache."""
            if data and len(data) > 1000 and data[:5] == b"%PDF-":
                cached.write_bytes(data)
                paper["_pdf_source"] = source
                try:
                    cached.with_suffix(".pdf.src").write_text(source, encoding="utf-8")
                except Exception:
                    pass
                if log:
                    label = _SOURCE_LABELS.get(source, source)
                    log(f"[PDF] {label} ({len(data)//1024}KB): {title}")
                return True
            # Record why data was rejected (only if data was non-None; _try_url
            # already records None-case failures with http_status / exception).
            if data is not None:
                if len(data) <= 1000:
                    PDFDownloader._record_failure(paper, source,
                                                  reason="content_too_small",
                                                  size=len(data))
                elif data[:5] != b"%PDF-":
                    PDFDownloader._record_failure(paper, source,
                                                  reason="not_pdf_content",
                                                  head=data[:8].hex())
            return False

        try:
            async with self._make_client(timeout=45.0) as client:

                # 0. GS sidebar PDF link (highest priority — GS already found the PDF)
                if gs_pdf_link:
                    url = _transform_url(gs_pdf_link)
                    cookies = _get_cookies_for_url(url)
                    data = await self._try_url(client, url, cookies, paper=paper, stage="gs_pdf")
                    if _ok(data, "gs_pdf"):
                        return cached

                # 1. OpenAlex OA PDF
                if oa_pdf_url:
                    data = await self._try_url(client, oa_pdf_url, paper=paper, stage="oa_pdf")
                    if _ok(data, "oa_pdf"):
                        return cached

                # 2. CVF open access (construct URL from metadata)
                first_author = ""
                authors_raw = paper.get("authors_raw") or {}
                if isinstance(authors_raw, dict):
                    for k in authors_raw:
                        m = re.match(r'author_\d+_(.*)', k)
                        if m:
                            first_author = m.group(1).split()[-1]
                            break
                cvf_urls = _build_cvf_candidates(doi, venue, year, full_title, first_author)
                for cvf_url in cvf_urls:
                    data = await self._try_url(client, cvf_url, paper=paper, stage="cvf")
                    if _ok(data, "cvf"):
                        return cached

                # 3. openAccessPdf (non-arxiv direct link)
                if pdf_url and "arxiv.org" not in pdf_url and "doi.org" not in pdf_url:
                    data = await self._try_url(client, pdf_url, paper=paper, stage="s2_page")
                    if _ok(data, "openaccess"):
                        return cached

                # 4. S2 API lookup (PaperRadar-style: always try if we have s2_id)
                if s2_id:
                    s2_data = await self._fetch_s2_data(client, s2_id, "")
                    if s2_data:
                        s2_pdf = (s2_data.get("openAccessPdf") or {}).get("url", "")
                        if s2_pdf:
                            data = await self._try_url(client, s2_pdf, paper=paper, stage="s2_page")
                            if _ok(data, "s2_page"):
                                return cached
                        else:
                            PDFDownloader._record_failure(paper, "s2_page", reason="no_oa_pdf_from_s2")
                        # Supplement: get ArXiv ID and DOI if not already set
                        ext = s2_data.get("externalIds") or {}
                        if not arxiv_id:
                            arxiv_id = ext.get("ArXiv", "")
                        if not doi:
                            doi = ext.get("DOI", "")
                    else:
                        PDFDownloader._record_failure(paper, "s2_page", reason="s2_api_no_result")

                # 5. DBLP conference lookup
                if full_title:
                    dblp_url = await self._fetch_dblp_pdf(client, full_title)
                    if dblp_url:
                        data = await self._try_url(client, dblp_url, _get_cookies_for_url(dblp_url),
                                                   paper=paper, stage="dblp")
                        if _ok(data, "dblp"):
                            return cached

                # 6. Sci-Hub
                if doi:
                    data = await self._try_scihub(client, doi)
                    if _ok(data, "scihub"):
                        return cached
                    if data is None:
                        PDFDownloader._record_failure(paper, "scihub", reason="no_mirror_returned_pdf")

                # 7. arXiv (rate-limited + retried — arxiv.org 429s hard under batch concurrency)
                if arxiv_id:
                    async with PDFDownloader._arxiv_sem:
                        data = await self._try_url_with_retry(
                            client, f"https://arxiv.org/pdf/{arxiv_id}", attempts=3,
                            paper=paper, stage="arxiv",
                        )
                    if _ok(data, "arxiv"):
                        return cached

                # 8. GS paper_link + smart URL transform
                if paper_link and "scholar.google" not in paper_link:
                    transformed = _transform_url(paper_link)
                    cookies = _get_cookies_for_url(transformed)
                    # MDPI is OA but occasionally 429s — wrap in retry
                    if "mdpi.com" in transformed:
                        data = await self._try_url_with_retry(
                            client, transformed, cookies, attempts=2,
                            paper=paper, stage="gs_link",
                        )
                    else:
                        data = await self._try_url(client, transformed, cookies,
                                                   paper=paper, stage="gs_link")
                    if _ok(data, "gs_link"):
                        return cached
                    # If transform didn't change URL, also try original
                    if transformed != paper_link:
                        cookies2 = _get_cookies_for_url(paper_link)
                        data = await self._try_url(client, paper_link, cookies2,
                                                   paper=paper, stage="gs_link")
                        if _ok(data, "gs_link"):
                            return cached

                # 9. curl + socks5 + Chrome cookies (for IEEE/Springer/ScienceDirect)
                # httpx can't use socks5h, but curl can — bypasses Cloudflare
                if paper_link and "scholar.google" not in paper_link:
                    data = await self._curl_publisher_download(paper_link)
                    if _ok(data, self._publisher_label(paper_link)):
                        return cached
                    if data is None:
                        PDFDownloader._record_failure(paper, "publisher_curl",
                                                      reason="curl_no_pdf",
                                                      url=paper_link[:120])

                # 10. DOI landing with cookie (via curl if socks available)
                if doi:
                    doi_url = f"https://doi.org/{doi}"
                    data = await self._curl_publisher_download(doi_url)
                    if _ok(data, self._publisher_label(doi_url)):
                        return cached
                    cookies = _get_cookies_for_url(doi_url)
                    data = await self._try_url(client, doi_url, cookies,
                                               paper=paper, stage="doi")
                    if _ok(data, "doi"):
                        return cached

                # 10. Unpaywall
                if doi:
                    data = await self._try_unpaywall(client, doi)
                    if _ok(data, "unpaywall"):
                        return cached
                    if data is None:
                        PDFDownloader._record_failure(paper, "unpaywall", reason="no_oa_url_from_unpaywall")

        except Exception as e:
            PDFDownloader._record_failure(paper, "pipeline_exception",
                                          error_type=type(e).__name__, detail=str(e))

        # 12-14. CDP browser sessions — serialized via lock (shared browser)
        if self._cdp_debug_port and paper_link:
            async with PDFDownloader._cdp_lock:
                # 12. CDP browser session — IEEE
                if "ieeexplore.ieee.org" in paper_link:
                    data = await self._try_cdp_ieee(paper, log)
                    if _ok(data, "CDP-IEEE"):
                        return cached
                    if data is None:
                        PDFDownloader._record_failure(paper, "CDP-IEEE",
                                                      reason="cdp_returned_none")

                # 13. CDP browser session — Elsevier
                if "sciencedirect.com" in paper_link or doi.startswith("10.1016/"):
                    data = await self._try_cdp_elsevier(paper, log)
                    if _ok(data, "CDP-Elsevier"):
                        return cached
                    if data is None:
                        PDFDownloader._record_failure(paper, "CDP-Elsevier",
                                                      reason="cdp_returned_none")

                # 14. CDP browser session — ACM Digital Library
                if "dl.acm.org" in paper_link or doi.startswith("10.1145/"):
                    data = await self._try_cdp_acm(paper, log)
                    if _ok(data, "CDP-ACM"):
                        return cached
                    if data is None:
                        PDFDownloader._record_failure(paper, "CDP-ACM",
                                                      reason="cdp_returned_none")
        elif paper_link and ("ieeexplore.ieee.org" in paper_link
                             or "sciencedirect.com" in paper_link
                             or "dl.acm.org" in paper_link
                             or doi.startswith("10.1016/")
                             or doi.startswith("10.1145/")):
            PDFDownloader._record_failure(paper, "CDP", reason="cdp_not_configured")

        return None

    # ── Helper: fetch S2 data by ID or title ──────────────────────────
    _s2_dl_lock = asyncio.Lock()  # Serialize S2 API calls in downloader

    async def _fetch_s2_data(self, client, s2_id: str, title: str) -> Optional[dict]:
        """Get S2 paper data (openAccessPdf, externalIds) by ID or title search."""
        try:
            if s2_id:
                url = f"https://api.semanticscholar.org/graph/v1/paper/{s2_id}?fields=openAccessPdf,externalIds"
            elif title:
                url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={quote(title)}&limit=1&fields=openAccessPdf,externalIds"
            else:
                return None
            async with self._s2_dl_lock:
                await asyncio.sleep(1.1)  # S2 rate limit: 1 req/s
                resp = await client.get(url, timeout=10)
            if resp.status_code != 200:
                return None
            data = resp.json()
            if "data" in data and data["data"]:  # Search result
                return data["data"][0]
            return data  # Direct paper result
        except Exception:
            return None

    # ── Helper: DBLP PDF lookup ───────────────────────────────────────
    async def _fetch_dblp_pdf(self, client, title: str) -> Optional[str]:
        """Query DBLP API for conference paper PDF URL."""
        try:
            api_url = f"https://dblp.org/search/publ/api?q={quote(title)}&format=json&h=3"
            resp = await client.get(api_url, timeout=10)
            if resp.status_code != 200:
                return None
            hits = resp.json().get("result", {}).get("hits", {}).get("hit", [])
            title_lower = title.lower().strip().rstrip(".")
            for hit in hits:
                info = hit.get("info", {})
                hit_title = (info.get("title") or "").lower().strip().rstrip(".")
                if hit_title != title_lower and title_lower not in hit_title:
                    continue
                ee = info.get("ee")
                if not ee:
                    continue
                urls = ee if isinstance(ee, list) else [ee]
                for venue_url in urls:
                    pdf_url = _transform_url(venue_url)
                    if pdf_url != venue_url or pdf_url.endswith(".pdf"):
                        return pdf_url
        except Exception:
            pass
        return None

    # ── Helper: Sci-Hub (uses curl+socks5 since httpx can't reach it) ──
    async def _try_scihub(self, client, doi: str) -> Optional[bytes]:
        """Try Sci-Hub mirrors for DOI. Uses curl+socks5 if available."""
        for mirror in SCIHUB_MIRRORS:
            try:
                data = await self._curl_scihub(mirror, doi)
                if data and data[:5] == b"%PDF-":
                    return data
            except Exception:
                continue

        # Fallback: try httpx (works if no socks needed)
        for mirror in SCIHUB_MIRRORS:
            try:
                resp = await client.get(f"{mirror}/{doi}", timeout=15)
                if resp.status_code != 200:
                    continue
                if resp.content[:5] == b"%PDF-":
                    return resp.content
                if "html" in resp.headers.get("content-type", ""):
                    html = resp.text
                    if "不可用" in html or "not available" in html.lower():
                        continue
                    pdf_url = _extract_scihub_pdf_url(html, str(resp.url))
                    if pdf_url:
                        r2 = await client.get(pdf_url, timeout=20)
                        if r2.status_code == 200 and r2.content[:5] == b"%PDF-":
                            return r2.content
            except Exception:
                continue
        return None

    async def _curl_scihub(self, mirror: str, doi: str) -> Optional[bytes]:
        """Download from Sci-Hub via curl+socks5."""
        if not _SOCKS_PROXY:
            return None

        def _do():
            try:
                # Step 1: Get Sci-Hub page
                r = subprocess.run([
                    'curl', '-x', _SOCKS_PROXY, '-s', '-L',
                    '-H', 'User-Agent: Mozilla/5.0',
                    f'{mirror}/{doi}'
                ], capture_output=True, timeout=20)
                if not r.stdout:
                    return None
                # Direct PDF?
                if r.stdout[:5] == b"%PDF-":
                    return r.stdout
                # Parse HTML for PDF URL
                html = r.stdout.decode('utf-8', errors='ignore')
                if "不可用" in html or "not available" in html.lower():
                    return None
                pdf_url = _extract_scihub_pdf_url(html, mirror)
                if not pdf_url:
                    return None
                # Step 2: Download PDF
                r2 = subprocess.run([
                    'curl', '-x', _SOCKS_PROXY, '-s', '-L',
                    '-H', 'User-Agent: Mozilla/5.0',
                    pdf_url
                ], capture_output=True, timeout=20)
                if r2.stdout and r2.stdout[:5] == b"%PDF-":
                    return r2.stdout
            except Exception:
                pass
            return None

        return await asyncio.to_thread(_do)

    # ── Helper: Unpaywall ─────────────────────────────────────────────
    async def _try_unpaywall(self, client, doi: str) -> Optional[bytes]:
        """Try Unpaywall API."""
        try:
            url = f"https://api.unpaywall.org/v2/{doi}?email={self._email}"
            resp = await client.get(url, timeout=10)
            if resp.status_code != 200:
                return None
            best = (resp.json().get("best_oa_location") or {}).get("url_for_pdf", "")
            if best:
                r2 = await client.get(best, timeout=20)
                if r2.status_code == 200 and r2.content[:5] == b"%PDF-":
                    return r2.content
        except Exception:
            pass
        return None

    # ── CDP: IEEE Xplore ──────────────────────────────────
    async def _try_cdp_ieee(self, paper: dict, log=None) -> Optional[bytes]:
        """Download IEEE paper via CDP browser session.

        Reuses an existing authenticated IEEE tab, or opens stamp.jsp and
        waits for user to complete authentication. Uses in-page fetch() to
        download getPDF.jsp with correct session cookies and Referer.
        """
        paper_link = _paper_link(paper)
        if not self._ensure_cdp_ready("CDP-IEEE", log):
            return None

        m = re.search(r'/document/(\d+)', paper_link)
        if not m:
            m = re.search(r'arnumber=(\d+)', paper_link)
        if not m:
            if log:
                log(f"  [CDP-IEEE] no arnumber found in link: {paper_link or '(empty)'}")
            return None
        arnumber = m.group(1)

        port = self._cdp_debug_port
        article_url = paper_link or f"https://ieeexplore.ieee.org/document/{arnumber}/"
        stamp_url = f"https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber={arnumber}"
        default_get_pdf_url = (
            f"https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber={arnumber}"
            f"&ref={quote(article_url, safe=':/?&=%')}"
        )

        def _sync():
            _log = log or (lambda msg: None)

            # Close leftover IEEE tabs from previous papers
            for t in _cdp_list_tabs(port):
                url_t = t.get("url", "")
                if t.get("type") == "page" and "ieeexplore.ieee.org" in url_t:
                    _cdp_close_page(port, t["id"])

            # Open a fresh user-visible paper tab for this article.
            _log(f"  [CDP-IEEE] opening article page (arnumber={arnumber})...")
            page = _cdp_open_page(port, article_url)
            ws_url = page.get("webSocketDebuggerUrl", "")
            if not ws_url:
                _log("  [CDP-IEEE] failed to get WebSocket URL")
                return None

            time.sleep(8)

            current = _cdp_evaluate(ws_url, "window.location.href", msg_id=5)
            _log(f"  [CDP-IEEE] page loaded: {str(current)[:80]}")

            # Detect auth needed: login page OR redirected away from stamp (e.g. homepage)
            def _has_paper_context(url_value) -> bool:
                if not url_value:
                    return False
                cur = str(url_value).lower()
                return (
                    "ieeexplore" in cur
                    and "login" not in cur
                    and "home.jsp" not in cur
                    and any(marker in cur for marker in (f"{arnumber}", "/document/", "stamp.jsp", "getpdf"))
                )

            needs_auth = not _has_paper_context(current)
            if current and False:
                cur_str = str(current).lower()
                if "login" in cur_str:
                    needs_auth = True
                elif "home.jsp" in cur_str:
                    needs_auth = True
                elif "stamp.jsp" not in cur_str and "getpdf" not in cur_str and "/document/" not in cur_str:
                    # Redirected to homepage or other non-stamp page — no session
                    _log("  [CDP-IEEE] redirected away from stamp page — session missing, navigating to login")
                    needs_auth = True

            if needs_auth:
                _log("  [CDP-IEEE] new tab is not in paper context yet, waiting for user authentication")
                # Navigate to login page explicitly if we're on homepage
                login_url = f"https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber={arnumber}"
                if False and current and "login" not in str(current).lower():
                    # On homepage — navigate to stamp again, which may redirect to login
                    _cdp_call(ws_url, "Page.navigate", {"url": login_url}, msg_id=8)
                    time.sleep(5)

                _log("  [CDP-IEEE] authentication required — complete login in the browser window (120s)")
                # Wait for auth (up to 120s)
                deadline = time.time() + 120
                last_msg = 0
                while time.time() < deadline:
                    if blocked_loops >= 3 and blocked_refreshes < 3:
                        blocked_refreshes += 1
                        blocked_loops = 0
                        _log(f"  [CDP-Elsevier] challenge page appears stuck, auto-refreshing article ({blocked_refreshes}/3)...")
                        _cdp_call(ws_url, "Page.navigate", {"url": article_url}, msg_id=13 + blocked_refreshes)
                        time.sleep(8)
                        continue
                    if blocked_loops >= 3 and blocked_refreshes < 3:
                        blocked_refreshes += 1
                        blocked_loops = 0
                        _log(f"  [CDP-Elsevier] challenge page appears stuck, auto-refreshing article ({blocked_refreshes}/3)...")
                        _cdp_call(ws_url, "Page.navigate", {"url": article_url}, msg_id=13 + blocked_refreshes)
                        time.sleep(8)
                        continue
                    time.sleep(3)
                    try:
                        url_now = _cdp_evaluate(ws_url, "window.location.href", msg_id=50)
                    except Exception:
                        time.sleep(2)
                        continue
                    now = time.time()
                    if now - last_msg > 15:
                        _log(f"  [CDP-IEEE] waiting for authentication... ({int(deadline - now)}s remaining)")
                        last_msg = now
                    if _has_paper_context(url_now):
                        break
                else:
                    _log("  [CDP-IEEE] auth timeout (120s)")
                    return None

                # Navigate back to stamp page after auth
                _log("  [CDP-IEEE] auth complete, navigating to stamp page...")
                _cdp_call(ws_url, "Page.navigate", {"url": stamp_url}, msg_id=6)
                time.sleep(8)

                # Verify — if still on login/homepage, try finding an authenticated tab
                check = _cdp_evaluate(ws_url, "window.location.href", msg_id=7)
                if not _has_paper_context(check):
                    _log(f"  [CDP-IEEE] stamp page did not reach paper context: {str(check)[:80]}")
                    return None

            html = _cdp_evaluate(ws_url, "document.documentElement.outerHTML", msg_id=9) or ""
            get_pdf_url = default_get_pdf_url
            for pat in [
                r'src=["\'](https?://[^"\']*getPDF[^"\']*)["\']',
                r'src=["\']([^"\']*getPDF\.jsp[^"\']*)["\']',
            ]:
                mm = re.search(pat, html, re.I)
                if mm:
                    candidate = mm.group(1)
                    if candidate.startswith("/"):
                        candidate = f"https://ieeexplore.ieee.org{candidate}"
                    elif candidate.startswith("//"):
                        candidate = f"https:{candidate}"
                    get_pdf_url = candidate
                    break

            _log(f"  [CDP-IEEE] fetching PDF from: {get_pdf_url[:120]}")
            data = _cdp_fetch_pdf_in_context(ws_url, get_pdf_url, log)
            if not data and get_pdf_url != default_get_pdf_url:
                _log("  [CDP-IEEE] extracted getPDF URL failed, retrying fallback URL")
                data = _cdp_fetch_pdf_in_context(ws_url, default_get_pdf_url, log)
            return data

        try:
            return await asyncio.to_thread(_sync)
        except Exception as e:
            if log:
                log(f"  [CDP-IEEE] exception: {type(e).__name__}: {e}")
            return None

    # ── CDP: Elsevier / ScienceDirect  ──────────────────────
    async def _try_cdp_elsevier(self, paper: dict, log=None) -> Optional[bytes]:
        """Download Elsevier paper via CDP browser session.

        Opens article page, extracts pdfDownload metadata, navigates to pdfft
        (user passes Cloudflare Turnstile if needed), then extracts original PDF
        from Edge's built-in PDF viewer via same-origin fetch on the S3 signed URL.
        """
        if not self._ensure_cdp_ready("CDP-Elsevier", log):
            return None

        link = _paper_link(paper)
        m = re.search(r'/pii/([A-Z0-9]+)', link)
        if not m:
            if log:
                log(f"  [CDP-Elsevier] no PII found in link: {link or '(empty)'}")
            return None
        target_pii = m.group(1)

        port = self._cdp_debug_port
        article_url = link or f"https://www.sciencedirect.com/science/article/pii/{target_pii}"

        def _sync():
            _log = log or (lambda msg: None)

            # Close leftover SD / PDF viewer tabs from previous papers
            for t in _cdp_list_tabs(port):
                url_t = t.get("url", "")
                tp = t.get("type", "")
                if tp == "page" and "sciencedirect.com" in url_t:
                    _cdp_close_page(port, t["id"])
                elif tp == "page" and "pdf.sciencedirectassets.com" in url_t:
                    _cdp_close_page(port, t["id"])
                elif tp == "webview" and "edge_pdf" in url_t:
                    _cdp_close_page(port, t["id"])

            page = _cdp_open_page(port, article_url)
            ws_url = page.get("webSocketDebuggerUrl", "")
            if not ws_url:
                _log("  [CDP-Elsevier] failed to open tab")
                return None

            time.sleep(8)

            # Extract pdfDownload metadata (with Cloudflare retry + auto-refresh, up to 90s)
            pdfft_url = None
            deadline_meta = time.time() + 90
            refresh_count = 0
            cloudflare_seen = False
            last_cf_log = 0
            blocked_loops = 0
            blocked_refreshes = 0
            while time.time() < deadline_meta:
                html = _cdp_evaluate(ws_url, "document.documentElement.outerHTML", msg_id=10)
                if not html:
                    time.sleep(3)
                    continue

                # Cloudflare challenge page?
                if "challenge-platform" in html or "Just a moment" in html or len(html) < 5000:
                    cloudflare_seen = True
                    blocked_loops += 1
                    now = time.time()
                    if log and now - last_cf_log > 10:
                        _log("  [CDP-Elsevier] page blocked by Cloudflare — complete verification in browser")
                        last_cf_log = now
                    if blocked_loops >= 3 and blocked_refreshes < 3:
                        blocked_refreshes += 1
                        blocked_loops = 0
                        _log(f"  [CDP-Elsevier] challenge page appears stuck, auto-refreshing article ({blocked_refreshes}/3)...")
                        _cdp_call(ws_url, "Page.navigate", {"url": article_url}, msg_id=13 + blocked_refreshes)
                        time.sleep(8)
                        continue
                    time.sleep(3)
                    continue

                # Cloudflare cleared — article page loaded
                if cloudflare_seen:
                    cloudflare_seen = False
                    blocked_loops = 0
                    _log("  [CDP-Elsevier] Cloudflare passed, loading article...")
                    # Auto-refresh after Cloudflare — page often stuck
                    _cdp_call(ws_url, "Page.navigate", {"url": article_url}, msg_id=12)
                    time.sleep(8)
                    continue

                mm = _SD_PDF_DOWNLOAD_RE.search(html)
                if mm:
                    md5, pid, found_pii, ext, path = mm.groups()
                    if found_pii != target_pii:
                        _cdp_call(ws_url, "Page.navigate", {"url": article_url}, msg_id=11)
                        time.sleep(8)
                        continue
                    pdfft_url = f"https://www.sciencedirect.com/{path}/{found_pii}{ext}?md5={md5}&pid={pid}"
                    _log("  [CDP-Elsevier] metadata found")
                    break

                # Metadata not found — auto-refresh (up to 2 times)
                if refresh_count < 2:
                    refresh_count += 1
                    _log(f"  [CDP-Elsevier] metadata not found, auto-refreshing ({refresh_count}/2)...")
                    _cdp_call(ws_url, "Page.navigate", {"url": article_url}, msg_id=12)
                    time.sleep(8)
                    continue

                if time.time() + 8 < deadline_meta:
                    time.sleep(5)
                    continue
                _log("  [CDP-Elsevier] pdfDownload metadata not found in article page")
                return None

            if not pdfft_url:
                return None

            # Navigate to pdfft (may trigger Cloudflare Turnstile)
            _log("  [CDP-Elsevier] navigating to pdfft — complete Cloudflare verification if prompted")
            _cdp_call(ws_url, "Page.navigate", {"url": pdfft_url}, msg_id=15)

            # Wait for Edge PDF viewer to appear with correct PII (up to 120s)
            deadline_pdf = time.time() + 120
            last_msg = 0
            pdfft_refreshes = 0
            next_pdfft_refresh_remaining = 90
            while time.time() < deadline_pdf:
                time.sleep(3)
                viewer = None
                pdf_page = None
                for t in _cdp_list_tabs(port):
                    if t.get("type") == "webview" and "edge_pdf" in t.get("url", ""):
                        viewer = t
                    if t.get("type") == "page" and "pdf.sciencedirectassets.com" in t.get("url", ""):
                        pdf_page = t

                if viewer and pdf_page:
                    try:
                        orig_url = _cdp_evaluate(
                            viewer["webSocketDebuggerUrl"],
                            'document.querySelector("embed").getAttribute("original-url")',
                            msg_id=30,
                        )
                        if orig_url and "pdf" in orig_url.lower():
                            if target_pii.upper() in orig_url.upper() or target_pii.upper() in pdf_page.get("url", "").upper():
                                data = _cdp_fetch_pdf_in_context(pdf_page["webSocketDebuggerUrl"], orig_url, log)
                                if data:
                                    # Clean up transient PDF viewer tabs. Keep the
                                    # article tab alive so the debug browser session
                                    # does not disappear between papers.
                                    _cdp_close_page(port, pdf_page["id"])
                                    _cdp_close_page(port, viewer["id"])
                                    return data
                    except Exception:
                        pass

                now = time.time()
                remaining = int(deadline_pdf - now)
                if log and now - last_msg > 15:
                    _log(f"  [CDP-Elsevier] waiting for PDF... ({remaining}s remaining)")
                    last_msg = now
                elif pdfft_refreshes < 2 and remaining <= next_pdfft_refresh_remaining:
                    pdfft_refreshes += 1
                    _log(f"  [CDP-Elsevier] PDF viewer still not ready, auto-refreshing pdfft ({pdfft_refreshes}/2)...")
                    _cdp_call(ws_url, "Page.navigate", {"url": pdfft_url}, msg_id=30 + pdfft_refreshes)
                    next_pdfft_refresh_remaining -= 30
                    time.sleep(6)

            return None

        for attempt in range(2):
            try:
                return await asyncio.to_thread(_sync)
            except RemoteDisconnected as e:
                if log:
                    log(f"  [CDP-Elsevier] transient disconnect (attempt {attempt+1}/2): {e}")
                if attempt == 0:
                    await asyncio.sleep(2)
                    continue
                return None
            except Exception as e:
                if log:
                    log(f"  [CDP-Elsevier] exception: {type(e).__name__}: {e}")
                return None
        return None

    # ── CDP: ACM Digital Library ──────────────────────
    async def _try_cdp_acm(self, paper: dict, log=None) -> Optional[bytes]:
        """Download ACM paper via CDP browser session.

        Opens the article landing page, waits for institutional auth if needed,
        then uses in-page fetch() against dl.acm.org/doi/pdf/{doi} with session
        cookies. Mirrors CDP-IEEE's control flow.
        """
        paper_link = _paper_link(paper)
        if not self._ensure_cdp_ready("CDP-ACM", log):
            return None

        # Extract ACM DOI (10.1145/xxx). Prefer paper["doi"] if available.
        doi_field = (paper.get("doi") or "").replace("https://doi.org/", "").strip()
        if doi_field.lower().startswith("10.1145/"):
            doi = doi_field
        else:
            m = re.search(r'(10\.1145/[^\s/?#]+)', paper_link or "")
            doi = m.group(1) if m else ""
        if not doi:
            if log:
                log(f"  [CDP-ACM] no ACM DOI (10.1145/...) found in link: {paper_link or '(empty)'}")
            return None

        port = self._cdp_debug_port
        article_url = f"https://dl.acm.org/doi/{doi}"
        pdf_url = f"https://dl.acm.org/doi/pdf/{doi}"

        def _sync():
            _log = log or (lambda msg: None)

            # Close leftover ACM tabs to avoid state pollution
            for t in _cdp_list_tabs(port):
                url_t = t.get("url", "")
                if t.get("type") == "page" and "dl.acm.org" in url_t:
                    _cdp_close_page(port, t["id"])

            _log(f"  [CDP-ACM] opening article page (doi={doi})...")
            page = _cdp_open_page(port, article_url)
            ws_url = page.get("webSocketDebuggerUrl", "")
            if not ws_url:
                _log("  [CDP-ACM] failed to get WebSocket URL")
                return None

            time.sleep(8)
            current = _cdp_evaluate(ws_url, "window.location.href", msg_id=5)
            _log(f"  [CDP-ACM] page loaded: {str(current)[:80]}")

            def _has_paper_context(url_value) -> bool:
                if not url_value:
                    return False
                cur = str(url_value).lower()
                return (
                    "dl.acm.org" in cur
                    and "showlogin" not in cur
                    and "dologin" not in cur
                    and (doi.lower() in cur or "/doi/" in cur)
                )

            if not _has_paper_context(current):
                _log("  [CDP-ACM] authentication required — complete login in the browser window (120s)")
                deadline = time.time() + 120
                last_msg = 0
                while time.time() < deadline:
                    time.sleep(3)
                    try:
                        url_now = _cdp_evaluate(ws_url, "window.location.href", msg_id=50)
                    except Exception:
                        time.sleep(2)
                        continue
                    now = time.time()
                    if now - last_msg > 15:
                        _log(f"  [CDP-ACM] waiting for authentication... ({int(deadline - now)}s remaining)")
                        last_msg = now
                    if _has_paper_context(url_now):
                        break
                else:
                    _log("  [CDP-ACM] auth timeout (120s)")
                    return None

            # Primary path: in-page fetch of direct PDF URL (authenticated session)
            _log(f"  [CDP-ACM] fetching PDF from: {pdf_url[:120]}")
            data = _cdp_fetch_pdf_in_context(ws_url, pdf_url, log)
            if data and data[:5] == b"%PDF-":
                return data

            # Fallback: navigate the tab to pdf_url so browser runs any JS
            # redirect / session warmup, then retry in-page fetch.
            _log("  [CDP-ACM] direct fetch did not return PDF, navigating tab to pdf URL...")
            _cdp_call(ws_url, "Page.navigate", {"url": pdf_url}, msg_id=10)
            time.sleep(10)
            data = _cdp_fetch_pdf_in_context(ws_url, pdf_url, log)
            return data

        try:
            return await asyncio.to_thread(_sync)
        except Exception as e:
            if log:
                log(f"  [CDP-ACM] exception: {type(e).__name__}: {e}")
            return None

    # ── Batch download ────────────────────────────────────────────────
    _PER_PAPER_TIMEOUT = 480  # 8 minutes max per paper


    async def batch_download(self, papers: List[dict], concurrency: int = 10,
                             log=None, label: str = "PDF下载",
                             per_paper_timeout: Optional[int] = None) -> List[Optional[Path]]:
        sem = asyncio.Semaphore(concurrency)
        stats = {"done": 0, "success": 0, "timeout": 0}
        stats_lock = asyncio.Lock()
        total = len(papers)
        timeout_seconds = per_paper_timeout or self._PER_PAPER_TIMEOUT

        async def _heartbeat():
            while True:
                await asyncio.sleep(60)
                async with stats_lock:
                    done = stats["done"]
                    success = stats["success"]
                    timeout = stats["timeout"]
                if done >= total:
                    return
                if log:
                    pending = total - done
                    log(f"[{label}] 仍在处理：已完成 {done}/{total}，成功 {success}，超时 {timeout}，剩余 {pending}")

        async def _dl(p):
            title = p.get("Paper_Title", p.get("title", "?"))[:40]
            async with sem:
                try:
                    result = await asyncio.wait_for(
                        self.download(p, log=log),
                        timeout=timeout_seconds,
                    )
                    async with stats_lock:
                        stats["done"] += 1
                        if result:
                            stats["success"] += 1
                    return result
                except asyncio.TimeoutError:
                    async with stats_lock:
                        stats["done"] += 1
                        stats["timeout"] += 1
                    if log:
                        log(f"[{label}] 单篇超时，已跳过: {title}")
                    return None

        heartbeat_task = asyncio.create_task(_heartbeat()) if log and total else None
        try:
            return await asyncio.gather(*[_dl(p) for p in papers])
        finally:
            if heartbeat_task:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass

    async def close(self):
        pass  # Client is created per-download via async context manager
