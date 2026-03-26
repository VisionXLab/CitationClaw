"""MinerU PDF parser — converts PDF to structured content + markdown.

Priority (4-tier):
  1. Cache (instant)
  2. MinerU Cloud Agent API (free, ≤10MB/≤20 pages, fast)
  3. MinerU Cloud Precision API (needs token, ≤200MB/≤600 pages)
  4. Local MinerU (needs GPU + models, slow first run)
  5. PyMuPDF (fast fallback, less structured)

Cloud APIs run on MinerU servers — no local GPU/model needed.
"""
import asyncio
import json
import os
import re
import hashlib
import logging
import time
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ── Auto-configure MinerU to use project-local models if available ─────
# This avoids re-downloading ~2GB models on every fresh environment.
# Priority: project-local models → ModelScope download (China-friendly)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_LOCAL_MODEL_DIR = _PROJECT_ROOT / "data" / "models" / "mineru"
_LOCAL_PIPELINE_DIR = _LOCAL_MODEL_DIR / "PDF-Extract-Kit-1.0"

if _LOCAL_PIPELINE_DIR.exists():
    # Models found in project directory — use local mode (no download)
    os.environ["MINERU_MODEL_SOURCE"] = "local"
    # Write project-scoped config for MinerU to find models
    _project_config = _PROJECT_ROOT / "data" / "models" / "mineru.json"
    _config_data = {
        "models-dir": {
            "pipeline": str(_LOCAL_PIPELINE_DIR),
        }
    }
    try:
        _project_config.write_text(json.dumps(_config_data, indent=2), encoding="utf-8")
        os.environ["MINERU_TOOLS_CONFIG_JSON"] = str(_project_config)
    except Exception:
        pass
else:
    # No local models — download from ModelScope on first use
    os.environ.setdefault("MINERU_MODEL_SOURCE", "modelscope")

# MinerU Cloud API endpoints
_AGENT_SUBMIT = "https://mineru.net/api/v1/agent/parse/file"
_AGENT_QUERY = "https://mineru.net/api/v1/agent/parse/{task_id}"
_PRECISION_SUBMIT = "https://mineru.net/api/v4/file-urls/batch"
_PRECISION_QUERY = "https://mineru.net/api/v4/extract-results/batch/{batch_id}"

# Limits
_AGENT_MAX_SIZE = 10 * 1024 * 1024   # 10 MB
_AGENT_MAX_PAGES = 20

# Shared lock for local MinerU — only 1 instance at a time (CPU/GPU heavy)
_local_mineru_lock = asyncio.Lock()


class MinerUParser:
    """Parse PDF using MinerU cloud API (primary), local MinerU, or PyMuPDF fallback."""

    def __init__(
        self,
        output_base: Path = Path("data/cache/pdf_parsed"),
        log_callback=None,
        mineru_api_token: str = "",
    ):
        self._output_base = output_base
        self._output_base.mkdir(parents=True, exist_ok=True)
        self._log = log_callback or logger.info
        self._mineru_token = mineru_api_token
        self._has_local_mineru = self._check_local_mineru()
        self._local_mineru_failed = False
        # Cloud API state:
        # _disabled = network unreachable, skip for entire session
        # Per-request failures (rate limit, file too large) do NOT disable — next file still tries
        self._cloud_agent_disabled = False
        self._cloud_precision_failed = False

    @staticmethod
    def _check_local_mineru() -> bool:
        try:
            from mineru.cli.client import do_parse
            return True
        except ImportError:
            return False

    def paper_key(self, paper: dict) -> str:
        """Generate a stable key for a paper."""
        key = paper.get("doi") or paper.get("Paper_Title") or paper.get("title") or "unknown"
        return hashlib.md5(key.encode()).hexdigest()[:16]

    def parse(self, pdf_path: Path, paper_key: str) -> Optional[dict]:
        """Parse PDF (sync — local MinerU → PyMuPDF only)."""
        output_dir = self._output_base / paper_key
        cached = self._load_cached(output_dir)
        if cached:
            return cached
        # Skip oversized PDFs
        file_size = pdf_path.stat().st_size if pdf_path.exists() else 0
        page_count = self._get_page_count(pdf_path)
        if file_size > 100 * 1024 * 1024 or page_count > 200:
            if self._log:
                self._log(f"    [PDF跳过] 文件过大 ({file_size // (1024*1024)}MB, {page_count}页)，跳过解析")
            return None
        if self._has_local_mineru and not self._local_mineru_failed:
            result = self._parse_local_mineru(pdf_path, output_dir)
            if result:
                return result
        return self._parse_pymupdf(pdf_path, output_dir)

    @staticmethod
    def _get_page_count(pdf_path: Path) -> int:
        """Quick page count via PyMuPDF (no full parse)."""
        try:
            import fitz
            import os, sys
            stderr_fd = sys.stderr.fileno()
            old_stderr = os.dup(stderr_fd)
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, stderr_fd)
            try:
                doc = fitz.open(str(pdf_path))
                n = len(doc)
                doc.close()
            finally:
                os.dup2(old_stderr, stderr_fd)
                os.close(old_stderr)
                os.close(devnull)
            return n
        except Exception:
            return 0

    async def parse_async(self, pdf_path: Path, paper_key: str) -> Optional[dict]:
        """Parse PDF with smart cloud-first routing.

        Priority: Cache → Cloud Agent → Cloud Precision → Local MinerU → PyMuPDF

        Smart behavior:
        - Small PDF (≤10MB, ≤20 pages): Agent first
        - Large PDF + has token: Precision first
        - Agent rate-limited on this file: fall through to Precision (next file still tries Agent)
        - Network unreachable: disable that cloud tier for entire session
        - All cloud fail: Local MinerU (serial) → PyMuPDF
        """
        output_dir = self._output_base / paper_key

        # 1. Cache
        cached = self._load_cached(output_dir)
        if cached:
            return cached

        file_size = pdf_path.stat().st_size if pdf_path.exists() else 0
        page_count = self._get_page_count(pdf_path)

        # Skip oversized PDFs (>100MB or >200 pages)
        if file_size > 100 * 1024 * 1024 or page_count > 200:
            if self._log:
                self._log(f"    [PDF跳过] 文件过大 ({file_size // (1024*1024)}MB, {page_count}页)，跳过解析")
            return None

        is_large = file_size > _AGENT_MAX_SIZE or page_count > _AGENT_MAX_PAGES

        # 2. Cloud routing — try both tiers with smart fallthrough
        if is_large and self._mineru_token and not self._cloud_precision_failed:
            # Large + has token → Precision first
            result = await self._parse_cloud_precision(pdf_path, output_dir)
            if result:
                return result
            # Precision failed → try Agent as fallback (may reject on size)
            if not self._cloud_agent_disabled:
                result = await self._parse_cloud_agent(pdf_path, output_dir)
                if result:
                    return result
        elif is_large and not self._mineru_token:
            # Large + no token → Agent will likely reject, try anyway then local
            if not self._cloud_agent_disabled:
                result = await self._parse_cloud_agent(pdf_path, output_dir)
                if result:
                    return result
        else:
            # Small file → Agent first
            if not self._cloud_agent_disabled:
                result = await self._parse_cloud_agent(pdf_path, output_dir)
                if result:
                    return result
            # Agent failed → try Precision if token available
            if self._mineru_token and not self._cloud_precision_failed:
                result = await self._parse_cloud_precision(pdf_path, output_dir)
                if result:
                    return result

        # 3. Local MinerU (serialized — only 1 at a time)
        if self._has_local_mineru and not self._local_mineru_failed:
            async with _local_mineru_lock:
                result = await asyncio.to_thread(
                    self._parse_local_mineru, pdf_path, output_dir
                )
                if result:
                    return result

        # 4. PyMuPDF fallback
        return self._parse_pymupdf(pdf_path, output_dir)

    # ── Cloud Agent API (free, ≤10MB/≤20 pages) ──────────────────────────

    @staticmethod
    def _make_direct_client(timeout: float = 120.0):
        """Create httpx client WITHOUT proxy — MinerU is a China service, no proxy needed."""
        import httpx
        return httpx.AsyncClient(
            proxy=None,
            trust_env=False,  # Ignore ALL_PROXY / socks5 env vars
            timeout=timeout,
            headers={"User-Agent": "CitationClaw/2.0"},
        )

    async def _parse_cloud_agent(self, pdf_path: Path, output_dir: Path) -> Optional[dict]:
        """Parse via MinerU Cloud Agent API (free, no auth needed, ≤10MB/≤20 pages)."""
        # Client-side pre-check to avoid uploading then getting rejected
        file_size = pdf_path.stat().st_size if pdf_path.exists() else 0
        if file_size > _AGENT_MAX_SIZE:
            self._log(f"    [Cloud Agent] 跳过: 文件 {file_size//1024//1024}MB > 10MB 限制")
            return None
        page_count = self._get_page_count(pdf_path)
        if page_count > _AGENT_MAX_PAGES:
            self._log(f"    [Cloud Agent] 跳过: {page_count} 页 > {_AGENT_MAX_PAGES} 页限制")
            return None

        try:
            client = self._make_direct_client(timeout=120.0)

            # Step 1: Request upload URL
            resp = await client.post(
                _AGENT_SUBMIT,
                json={"file_name": pdf_path.name, "language": "en"},
            )
            if resp.status_code != 200:
                self._log(f"    [Cloud Agent] 提交失败: HTTP {resp.status_code}")
                # 401/403 = permanent; 429 = rate limit (temporary); others = temporary
                if resp.status_code in (401, 403):
                    self._cloud_agent_disabled = True
                await client.aclose()
                return None
            body = resp.json()
            if body.get("code") != 0:
                msg = body.get('msg', '未知错误')
                self._log(f"    [Cloud Agent] 提交失败: {msg}")
                await client.aclose()
                return None
            data = body.get("data", {})
            task_id = data.get("task_id", "")
            file_url = data.get("file_url", "")
            if not task_id or not file_url:
                self._log("    [Cloud Agent] 提交失败: 未返回 task_id 或 file_url")
                await client.aclose()
                return None

            # Step 2: Upload PDF via PUT
            pdf_bytes = pdf_path.read_bytes()
            # OSS pre-signed URL — do NOT set Content-Type (signature mismatch)
            put_resp = await client.put(file_url, content=pdf_bytes)
            if put_resp.status_code not in (200, 201):
                self._log(f"    [Cloud Agent] 上传失败: HTTP {put_resp.status_code}")
                await client.aclose()
                return None

            # Step 3: Poll for result
            md_url = await self._poll_agent(client, task_id)
            if not md_url:
                self._log(f"    [Cloud Agent] 轮询超时或失败 (task_id={task_id[:16]})")
                await client.aclose()
                return None

            # Step 4: Download markdown
            md_resp = await client.get(md_url)
            await client.aclose()
            if md_resp.status_code != 200:
                self._log(f"    [Cloud Agent] 下载 markdown 失败: HTTP {md_resp.status_code}")
                return None
            md_text = md_resp.text

            # Save to cache
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "full.md").write_text(md_text, encoding="utf-8")

            return {
                "content_list": [],
                "full_md": md_text,
                "first_page_blocks": self._md_to_first_page(md_text),
                "references_md": self._extract_references(md_text),
                "source": "mineru_cloud_agent",
                "parsed_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            err = str(e)[:80]
            self._log(f"    [Cloud Agent] 异常: {err}")
            # Network errors → disable cloud agent for entire session
            if any(k in err.lower() for k in ["connect", "refused", "resolve", "ssl"]):
                self._cloud_agent_disabled = True
                self._log("    [Cloud Agent] 网络不可达，本次运行后续跳过 Cloud Agent")
            # Timeout = temporary, don't disable (next file still tries)
            return None

    async def _poll_agent(self, client, task_id: str, max_wait: int = 120) -> Optional[str]:
        """Poll Agent API until done. Returns markdown_url or None."""
        url = _AGENT_QUERY.format(task_id=task_id)
        start = time.monotonic()
        while time.monotonic() - start < max_wait:
            try:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return None
                body = resp.json()
                data = body.get("data", {})
                state = data.get("state", "")
                if state == "done":
                    return data.get("markdown_url", "")
                if state == "failed":
                    self._log(f"    [Cloud Agent] 解析失败: {data.get('err_msg', '')[:60]}")
                    return None
            except Exception:
                pass
            await asyncio.sleep(3)
        return None

    # ── Cloud Precision API (needs token, ≤200MB/≤600 pages) ─────────────

    async def _parse_cloud_precision(self, pdf_path: Path, output_dir: Path) -> Optional[dict]:
        """Parse via MinerU Cloud Precision API (requires Bearer token)."""
        try:
            client = self._make_direct_client(timeout=180.0)
            headers = {
                "Authorization": f"Bearer {self._mineru_token}",
                "Content-Type": "application/json",
            }

            # Step 1: Get upload URL
            resp = await client.post(
                _PRECISION_SUBMIT,
                json={
                    "files": [{"name": pdf_path.name, "data_id": "f1"}],
                    "model_version": "pipeline",
                    "enable_formula": False,
                    "enable_table": False,
                    "is_ocr": False,
                },
                headers=headers,
            )
            if resp.status_code != 200:
                self._log(f"    [Cloud Precision] 提交失败: HTTP {resp.status_code}")
                if resp.status_code in (401, 403):
                    self._log("    [Cloud Precision] Token 无效或过期，后续跳过")
                    self._cloud_precision_failed = True
                await client.aclose()
                return None
            body = resp.json()
            if body.get("code") != 0:
                self._log(f"    [Cloud Precision] 提交失败: {body.get('msg', '')[:60]}")
                await client.aclose()
                return None
            data = body.get("data", {})
            batch_id = data.get("batch_id", "")
            file_urls = data.get("file_urls", [])
            if not batch_id or not file_urls:
                self._log("    [Cloud Precision] 未返回 batch_id 或 file_urls")
                await client.aclose()
                return None

            # Step 2: Upload PDF (no Content-Type — OSS pre-signed URL)
            pdf_bytes = pdf_path.read_bytes()
            put_resp = await client.put(file_urls[0], content=pdf_bytes)
            if put_resp.status_code not in (200, 201):
                self._log(f"    [Cloud Precision] 上传失败: HTTP {put_resp.status_code}")
                await client.aclose()
                return None

            # Step 3: Poll for result
            result_url = await self._poll_precision(client, batch_id, headers)
            if not result_url:
                self._log(f"    [Cloud Precision] 轮询超时或失败 (batch={batch_id[:16]})")
                await client.aclose()
                return None

            # Step 4: Download result zip
            zip_resp = await client.get(result_url)
            await client.aclose()
            if zip_resp.status_code != 200:
                return None

            return self._extract_from_zip(zip_resp.content, output_dir)

        except Exception as e:
            err = str(e)[:80]
            self._log(f"    [Cloud Precision] 异常: {err}")
            if any(k in err.lower() for k in ["timeout", "connect", "refused", "resolve"]):
                self._cloud_precision_failed = True
            return None

    async def _poll_precision(self, client, batch_id: str, headers: dict,
                               max_wait: int = 300) -> Optional[str]:
        """Poll Precision API. Returns full_zip_url or None."""
        url = _PRECISION_QUERY.format(batch_id=batch_id)
        start = time.monotonic()
        while time.monotonic() - start < max_wait:
            try:
                resp = await client.get(url, headers=headers)
                if resp.status_code != 200:
                    self._log(f"    [Cloud Precision] 轮询 HTTP {resp.status_code}")
                    return None
                data = resp.json().get("data", {})
                # Response: data.extract_result = [{file_name, state, full_zip_url}]
                results = data.get("extract_result", [])
                if not results:
                    await asyncio.sleep(5)
                    continue
                file_result = results[0]
                state = file_result.get("state", "")
                if state == "done":
                    return file_result.get("full_zip_url", "")
                if state == "failed":
                    err = file_result.get("err_msg", "")
                    self._log(f"    [Cloud Precision] 解析失败: {err[:60]}")
                    return None
                # state is "pending" or "running" — show progress if available
                progress = file_result.get("extract_progress", {})
                if progress:
                    extracted = progress.get("extracted_pages", 0)
                    total = progress.get("total_pages", 0)
                    if total > 0:
                        self._log(f"    [Cloud Precision] 解析中 {extracted}/{total} 页...")
            except Exception:
                pass
            await asyncio.sleep(5)
        return None

    def _extract_from_zip(self, zip_bytes: bytes, output_dir: Path) -> Optional[dict]:
        """Extract markdown + content_list from Precision API zip response."""
        import zipfile
        import io

        output_dir.mkdir(parents=True, exist_ok=True)
        md_text = ""
        content_list = []

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for name in zf.namelist():
                if name.endswith('.md'):
                    md_text = zf.read(name).decode('utf-8')
                    (output_dir / "full.md").write_text(md_text, encoding="utf-8")
                elif 'content_list' in name and name.endswith('.json'):
                    content_list = json.loads(zf.read(name))
                    (output_dir / "content_list.json").write_text(
                        json.dumps(content_list, ensure_ascii=False), encoding="utf-8"
                    )

        if not md_text:
            return None

        return {
            "content_list": content_list,
            "full_md": md_text,
            "first_page_blocks": (
                [b for b in content_list if b.get("page_idx", 99) == 0][:20]
                if content_list else self._md_to_first_page(md_text)
            ),
            "references_md": self._extract_references(md_text),
            "source": "mineru_cloud_precision",
            "parsed_at": datetime.now(timezone.utc).isoformat(),
        }

    # ── Local MinerU (needs GPU + models) ─────────────────────────────────

    def _parse_local_mineru(self, pdf_path: Path, output_dir: Path) -> Optional[dict]:
        """Parse with local MinerU Python API (runs under _local_mineru_lock)."""
        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            from mineru.cli.client import do_parse

            pdf_bytes = pdf_path.read_bytes()
            do_parse(
                output_dir=str(output_dir),
                pdf_file_names=[pdf_path.name],
                pdf_bytes_list=[pdf_bytes],
                p_lang_list=["en"],
                backend="pipeline",
                parse_method="txt",
                f_dump_md=True,
                f_dump_content_list=True,
                f_dump_model_output=False,
                f_dump_orig_pdf=False,
                f_draw_layout_bbox=False,
                f_draw_span_bbox=False,
                f_dump_middle_json=False,
            )

            content_list = []
            for f in output_dir.rglob("*content_list.json"):
                with open(f) as fh:
                    content_list = json.load(fh)
                break

            md_text = ""
            for f in output_dir.rglob("*.md"):
                md_text = f.read_text(encoding="utf-8")
                std_path = output_dir / "full.md"
                if f != std_path:
                    std_path.write_text(md_text, encoding="utf-8")
                break

            if not md_text and not content_list:
                return None

            # First successful local parse → symlink models to project for next time
            self._ensure_project_model_link()

            return {
                "content_list": content_list,
                "full_md": md_text,
                "first_page_blocks": (
                    [b for b in content_list if b.get("page_idx", 99) == 0][:20]
                ),
                "references_md": self._extract_references(md_text),
                "source": "mineru_local",
                "parsed_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            error_msg = str(e)
            if any(k in error_msg.lower() for k in [
                "no such file", "model", "ultralytics", "doclayout",
                "not found", "cannot import", "modulenotfounderror"
            ]):
                self._log(
                    f"  ⚠ 本地 MinerU 不可用 ({error_msg[:80]}...)，后续跳过"
                )
                self._local_mineru_failed = True
            else:
                self._log(f"  ⚠ 本地 MinerU 解析失败: {error_msg[:80]}...")
            return None

    @staticmethod
    def _ensure_project_model_link():
        """After first successful local MinerU parse, symlink models into project.

        So next startup uses MINERU_MODEL_SOURCE=local (no download).
        """
        if _LOCAL_PIPELINE_DIR.exists():
            return  # Already linked
        # Find where ModelScope downloaded the models
        ms_cache = Path.home() / ".cache" / "modelscope" / "hub" / "models" / "OpenDataLab"
        candidates = [
            ms_cache / "PDF-Extract-Kit-1___0",
            ms_cache / "PDF-Extract-Kit-1.0",
        ]
        for src in candidates:
            if src.exists() and src.is_dir():
                try:
                    _LOCAL_MODEL_DIR.mkdir(parents=True, exist_ok=True)
                    _LOCAL_PIPELINE_DIR.symlink_to(src)
                    logger.info(f"MinerU 模型已链接到项目: {_LOCAL_PIPELINE_DIR} → {src}")
                except Exception:
                    pass
                return

    # ── PyMuPDF fallback ──────────────────────────────────────────────────

    def _parse_pymupdf(self, pdf_path: Path, output_dir: Path) -> Optional[dict]:
        """Fallback: simple PyMuPDF text extraction."""
        try:
            import fitz
            import os, sys
            stderr_fd = sys.stderr.fileno()
            old_stderr = os.dup(stderr_fd)
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, stderr_fd)
            try:
                doc = fitz.open(str(pdf_path))
                pages = [page.get_text() for page in doc]
                doc.close()
            finally:
                os.dup2(old_stderr, stderr_fd)
                os.close(old_stderr)
                os.close(devnull)

            full_text = "\n\n".join(pages)
            first_page = pages[0] if pages else ""

            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "full.md").write_text(full_text, encoding="utf-8")

            return {
                "content_list": [],
                "full_md": full_text,
                "first_page_blocks": self._md_to_first_page(first_page),
                "references_md": self._extract_references(full_text),
                "source": "pymupdf",
                "parsed_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception:
            return None

    # ── Shared utilities ──────────────────────────────────────────────────

    def _load_cached(self, output_dir: Path) -> Optional[dict]:
        """Load previously parsed result from cache directory."""
        md_path = output_dir / "full.md"
        if not md_path.exists():
            md_files = list(output_dir.rglob("*.md"))
            if md_files:
                md_path = md_files[0]
            else:
                return None
        try:
            md_text = md_path.read_text(encoding="utf-8")
            content_list = []
            for f in output_dir.rglob("*content_list.json"):
                with open(f) as fh:
                    content_list = json.load(fh)
                break
            return {
                "content_list": content_list,
                "full_md": md_text,
                "first_page_blocks": (
                    [b for b in content_list if b.get("page_idx", 99) == 0][:20]
                    if content_list else self._md_to_first_page(md_text)
                ),
                "references_md": self._extract_references(md_text),
                "source": "mineru" if content_list else "pymupdf",
                "parsed_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception:
            return None

    @staticmethod
    def _md_to_first_page(text: str) -> list:
        """Convert first-page text to pseudo content blocks."""
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        return [{"type": "text", "text": l, "page_idx": 0} for l in lines[:20]]

    @staticmethod
    def _extract_references(text: str) -> str:
        """Extract References/Bibliography section from text."""
        match = re.search(r'(?:^|\n)\s*(?:References|Bibliography|REFERENCES)\s*\n',
                          text, re.MULTILINE)
        if match:
            return text[match.start():]
        return ""
