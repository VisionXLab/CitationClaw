# Phase 1 Citation Scraping Cache Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a persistent, cross-run cache for Phase 1 (Google Scholar citation scraping) so that already-scraped papers are never fetched again — both in normal pagination mode and year-traversal mode.

**Architecture:** A new `Phase1Cache` class (modelled on `AuthorInfoCache`) stores papers keyed by `paper_link` (or title fallback) under each target URL. The scraper gains an optional `page_callback` that writes to the cache after each page. `phase1_citation_fetch.py` checks the cache before scraping, skips complete entries, and marks entries complete when done. Year-traversal mode tracks completion per year.

**Tech Stack:** Python asyncio, JSON (same as other caches), pathlib

---

### Task 1: Create `Phase1Cache` class

**Files:**
- Create: `citationclaw/core/phase1_cache.py`

**Step 1: Write the file**

```python
"""
持久化 Phase 1 引用爬取缓存。

跨多次运行复用已爬取的引用论文列表，避免重复调用 ScraperAPI。

缓存文件：data/cache/phase1_cache.json
缓存 key：Google Scholar 引用页 URL（原始值，不做标准化）
缓存永久有效，由用户手动清除缓存文件来重置。
"""
import json
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional

DEFAULT_CACHE_FILE = Path("data/cache/phase1_cache.json")


class Phase1Cache:
    """跨运行持久化 Phase 1 引用爬取结果缓存。"""

    def __init__(self, cache_file: Path = DEFAULT_CACHE_FILE):
        self.cache_file = cache_file
        self._data: dict = {}
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0
        self._load()

    # ─── 内部 ────────────────────────────────────────────────────────────────

    def _load(self):
        if self.cache_file.exists():
            try:
                self._data = json.loads(self.cache_file.read_text(encoding="utf-8"))
            except Exception:
                self._data = {}
        else:
            self._data = {}

    async def _save(self):
        """将内存数据写入磁盘（调用方须已持有 _lock）。"""
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self.cache_file.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _paper_key(paper_link: str, paper_title: str) -> str:
        """生成论文去重 key：优先用链接，无链接用小写标题。"""
        key = (paper_link or "").strip()
        if not key:
            key = (paper_title or "").strip().lower()
        return key

    def _entry(self, url: str) -> dict:
        """获取或创建 URL 对应的缓存条目。"""
        if url not in self._data:
            self._data[url] = {
                "url": url,
                "complete": False,
                "mode": "normal",
                "updated_at": datetime.now().isoformat(),
                "papers": {},
                "years": {},
            }
        return self._data[url]

    # ─── 查询 ─────────────────────────────────────────────────────────────────

    def is_complete(self, url: str) -> bool:
        entry = self._data.get(url)
        if entry and entry.get("complete"):
            self._hits += 1
            return True
        self._misses += 1
        return False

    def is_year_complete(self, url: str, year: int) -> bool:
        entry = self._data.get(url, {})
        return entry.get("years", {}).get(str(year), {}).get("complete", False)

    def get_missing_years(self, url: str, all_years: list) -> list:
        """返回 all_years 中尚未完整缓存的年份列表。"""
        entry = self._data.get(url, {})
        cached_years = entry.get("years", {})
        return [y for y in all_years if not cached_years.get(str(y), {}).get("complete", False)]

    def has_papers(self, url: str) -> bool:
        entry = self._data.get(url, {})
        return bool(entry.get("papers"))

    def stats(self) -> dict:
        return {
            "total_entries": len(self._data),
            "hits": self._hits,
            "misses": self._misses,
        }

    # ─── 写入 ─────────────────────────────────────────────────────────────────

    async def add_papers(self, url: str, paper_dict: dict, year: Optional[int] = None):
        """
        将一页的 paper_dict 去重写入缓存，立即落盘。

        paper_dict 格式：{"paper_0": {"paper_link": ..., "paper_title": ..., ...}, ...}
        year：仅年份遍历模式下传入，用于标记 mode="year_traverse"。
        """
        if not paper_dict:
            return
        async with self._lock:
            entry = self._entry(url)
            if year is not None:
                entry["mode"] = "year_traverse"
            papers = entry["papers"]
            for paper_data in paper_dict.values():
                link = (paper_data.get("paper_link") or "").strip()
                title = (paper_data.get("paper_title") or "").strip()
                key = self._paper_key(link, title)
                if key and key not in papers:
                    papers[key] = paper_data
            entry["updated_at"] = datetime.now().isoformat()
            await self._save()

    async def mark_year_complete(self, url: str, year: int):
        """标记某年份已完整爬取。"""
        async with self._lock:
            entry = self._entry(url)
            entry["mode"] = "year_traverse"
            entry["years"].setdefault(str(year), {})["complete"] = True
            entry["updated_at"] = datetime.now().isoformat()
            await self._save()

    async def mark_complete(self, url: str):
        """标记整个 URL 已完整爬取。"""
        async with self._lock:
            entry = self._entry(url)
            entry["complete"] = True
            entry["updated_at"] = datetime.now().isoformat()
            await self._save()

    # ─── JSONL 重建 ───────────────────────────────────────────────────────────

    def build_jsonl(self, url: str) -> str:
        """
        从缓存重建 JSONL 字符串，格式与 scraper 原生输出完全一致，供 Phase 2 读取。

        每行格式：{"page_N": {"paper_dict": {10 papers}, "next_page": null}}
        每页 10 篇论文（与 Google Scholar 分页对齐）。
        """
        entry = self._data.get(url, {})
        all_papers = list(entry.get("papers", {}).values())

        page_size = 10
        lines = []
        for page_idx in range(0, max(1, len(all_papers)), page_size):
            batch = all_papers[page_idx: page_idx + page_size]
            paper_dict = {f"paper_{i}": p for i, p in enumerate(batch)}
            record = {"paper_dict": paper_dict, "next_page": None}
            lines.append(json.dumps({f"page_{page_idx // page_size}": record}, ensure_ascii=False))

        return "\n".join(lines) + "\n" if lines else ""
```

**Step 2: Commit**

```bash
git add citationclaw/core/phase1_cache.py
git commit -m "feat: add Phase1Cache for persistent cross-run citation scraping cache"
```

---

### Task 2: Add `page_callback` to `scraper.py`

**Files:**
- Modify: `citationclaw/core/scraper.py`

**Context:** There are two write points:
- Line ~816: inside `_scrape_single_year()` — year-traverse mode
- Line ~1228: inside `scrape()` — normal mode

Both write `f.write(json.dumps({f'page_{page_count}': record}, ...) + '\n')` then `f.flush()`.

**Step 1: Add `page_callback` to `_scrape_single_year` signature (line 573)**

Find:
```python
async def _scrape_single_year(
    self,
    base_url: str,
    year: int,
    output_file: Path,
    sleep_seconds: int = 10,
    cancel_check: Optional[Callable[[], bool]] = None,
    expected_count: int = 0
) -> dict:
```

Replace with:
```python
async def _scrape_single_year(
    self,
    base_url: str,
    year: int,
    output_file: Path,
    sleep_seconds: int = 10,
    cancel_check: Optional[Callable[[], bool]] = None,
    expected_count: int = 0,
    page_callback: Optional[Callable] = None,
) -> dict:
```

**Step 2: Call `page_callback` after the write in `_scrape_single_year` (line ~816)**

Find (inside `_scrape_single_year`):
```python
                f.write(json.dumps({f'page_{page_count}': record}, ensure_ascii=False) + '\n')
                f.flush()

                # 准备下一页
```

Replace with:
```python
                f.write(json.dumps({f'page_{page_count}': record}, ensure_ascii=False) + '\n')
                f.flush()
                if page_callback:
                    await page_callback(paper_dict, year)

                # 准备下一页
```

**Step 3: Add `page_callback` to `scrape()` signature (line 836)**

Find:
```python
    async def scrape(
        self,
        url: str,
        output_file: Path,
        start_page: int = 0,
        sleep_seconds: int = 10,
        cancel_check: Optional[Callable[[], bool]] = None,
        enable_year_traverse: bool = False
    ):
```

Replace with:
```python
    async def scrape(
        self,
        url: str,
        output_file: Path,
        start_page: int = 0,
        sleep_seconds: int = 10,
        cancel_check: Optional[Callable[[], bool]] = None,
        enable_year_traverse: bool = False,
        page_callback: Optional[Callable] = None,
    ):
```

**Step 4: Pass `page_callback` through to `_scrape_single_year` in `scrape()` (line ~903)**

Find:
```python
                        stats = await self._scrape_single_year(
                            base_url=url,
                            year=year,
                            output_file=temp_file,
                            sleep_seconds=sleep_seconds,
                            cancel_check=cancel_check,
                            expected_count=expected_count
                        )
```

Replace with:
```python
                        stats = await self._scrape_single_year(
                            base_url=url,
                            year=year,
                            output_file=temp_file,
                            sleep_seconds=sleep_seconds,
                            cancel_check=cancel_check,
                            expected_count=expected_count,
                            page_callback=page_callback,
                        )
```

**Step 5: Call `page_callback` after the write in normal-mode `scrape()` (line ~1228)**

Find (inside `scrape()` normal mode loop):
```python
                f.write(json.dumps({f'page_{page_count}': record}, ensure_ascii=False) + '\n')
                f.flush()  # 立即写入磁盘

                self.log_callback(f"✅ 第 {page_count} 页完成
```

Replace with:
```python
                f.write(json.dumps({f'page_{page_count}': record}, ensure_ascii=False) + '\n')
                f.flush()  # 立即写入磁盘
                if page_callback:
                    await page_callback(paper_dict, None)

                self.log_callback(f"✅ 第 {page_count} 页完成
```

**Step 6: Commit**

```bash
git add citationclaw/core/scraper.py
git commit -m "feat: add optional page_callback to scraper for per-page cache integration"
```

---

### Task 3: Integrate cache into `phase1_citation_fetch.py`

**Files:**
- Modify: `citationclaw/skills/phase1_citation_fetch.py`

**Context:** Current `run()` method (61 lines total):
- Lines 38-46: `probe_only` early return
- Lines 48-49: validate `output_file`
- Lines 51-59: call `scraper.scrape()`
- Line 60: return result

**Step 1: Add import at top of file**

After `from citationclaw.skills.base import SkillContext, SkillResult`:
```python
from citationclaw.core.phase1_cache import Phase1Cache
```

**Step 2: Replace the `run()` body (after probe_only block)**

Replace lines 48-60 (from `if output_file is None:` to the final `return`) with:

```python
        if output_file is None:
            raise ValueError("phase1_citation_fetch requires output_file when probe_only=False")

        out = Path(output_file)
        cache = Phase1Cache()

        # ── 完整缓存命中：直接从缓存重建 JSONL，跳过爬虫 ──────────────────
        if cache.is_complete(url):
            ctx.log(f"💾 [Phase1缓存] 命中完整缓存，跳过爬取: {url[:60]}...")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(cache.build_jsonl(url), encoding="utf-8")
            stats = cache.stats()
            ctx.log(f"💾 Phase1缓存复用: {len(cache._data.get(url, {}).get('papers', {}))} 篇论文")
            return SkillResult(name=self.name, data={"output_file": str(out), "from_cache": True})

        # ── 定义 page_callback：每页写入缓存 ──────────────────────────────
        async def on_page(paper_dict: dict, year):
            await cache.add_papers(url, paper_dict, year=year)

        # ── 年份遍历模式：跳过已完整缓存的年份 ───────────────────────────
        # 注意：年份列表由 scraper 内部从 HTML 提取，此处通过 year_skip_check 回调传递信息
        # 实现方式：在 scraper 调用前后，通过 cache.get_missing_years 过滤
        # 由于 scraper 内部决定年份列表，此处采用 post-year callback 标记完成
        async def on_year_complete(year: int):
            await cache.mark_year_complete(url, year)

        await scraper.scrape(
            url=url,
            output_file=out,
            start_page=start_page,
            sleep_seconds=sleep_seconds,
            cancel_check=ctx.cancel_check,
            enable_year_traverse=enable_year_traverse,
            page_callback=on_page,
            year_complete_callback=on_year_complete,
            cached_years=set(
                int(y) for y, v in cache._data.get(url, {}).get("years", {}).items()
                if v.get("complete")
            ) if enable_year_traverse else None,
        )

        # ── 标记完整完成（仅在未取消时）──────────────────────────────────
        if not (ctx.cancel_check and ctx.cancel_check()):
            await cache.mark_complete(url)
            ctx.log(f"💾 Phase1缓存已保存: {len(cache._data.get(url, {}).get('papers', {}))} 篇论文")

        return SkillResult(name=self.name, data={"output_file": str(out), "from_cache": False})
```

**Step 3: Add `year_complete_callback` and `cached_years` to `scraper.scrape()` signature**

Go back to `citationclaw/core/scraper.py`. Add two more optional params to `scrape()`:

```python
    async def scrape(
        self,
        url: str,
        output_file: Path,
        start_page: int = 0,
        sleep_seconds: int = 10,
        cancel_check: Optional[Callable[[], bool]] = None,
        enable_year_traverse: bool = False,
        page_callback: Optional[Callable] = None,
        year_complete_callback: Optional[Callable] = None,
        cached_years: Optional[set] = None,
    ):
```

In the year-traverse loop (around line 887), after the year is fetched and before `_scrape_single_year` is called, add a skip check:

Find:
```python
                    for idx, (year, expected_count) in enumerate(year_data):
                        # 检查是否取消
                        if cancel_check and cancel_check():
                            self.log_callback("任务已取消")
                            break
```

Replace with:
```python
                    for idx, (year, expected_count) in enumerate(year_data):
                        # 检查是否取消
                        if cancel_check and cancel_check():
                            self.log_callback("任务已取消")
                            break

                        # 跳过已完整缓存的年份
                        if cached_years and year in cached_years:
                            self.log_callback(f"💾 [Phase1缓存] {year} 年已缓存，跳过")
                            self.progress_callback(idx + 1, len(year_data))
                            continue
```

After `year_stats.append(stats)` (line ~912), call the year complete callback:

```python
                        year_stats.append(stats)
                        total_papers_all_years += stats['papers']
                        if year_complete_callback and not (cancel_check and cancel_check()):
                            await year_complete_callback(year)
```

**Step 4: Commit both files**

```bash
git add citationclaw/skills/phase1_citation_fetch.py citationclaw/core/scraper.py
git commit -m "feat: integrate Phase1Cache into citation fetch skill with year-level granularity"
```

---

### Task 4: Verify compatibility

**Goal:** Confirm no existing callers are broken.

**Step 1: Check all callers of `scraper.scrape()`**

Run:
```bash
grep -rn "\.scrape(" citationclaw/ --include="*.py"
```

Expected: only `phase1_citation_fetch.py` calls `scraper.scrape()`. All new params have defaults, so no other callers are affected.

**Step 2: Check all callers of `_scrape_single_year()`**

Run:
```bash
grep -rn "_scrape_single_year" citationclaw/ --include="*.py"
```

Expected: only called internally within `scraper.py`. New param has default `None`.

**Step 3: Check cache file location is consistent**

Run:
```bash
python3 -c "from citationclaw.core.phase1_cache import Phase1Cache; c = Phase1Cache(); print(c.cache_file)"
```

Expected: `data/cache/phase1_cache.json`

**Step 4: Verify `build_jsonl` output format matches Phase 2 expectations**

Check that `author_searcher.py` reads the JSONL with:
```bash
grep -n "paper_dict\|next_page\|page_" citationclaw/core/author_searcher.py | head -20
```

Confirm output format is `{"page_N": {"paper_dict": {...}, "next_page": ...}}` per line.

**Step 5: Commit if any minor fixes needed, otherwise just note results**

```bash
git add -A
git commit -m "fix: phase1 cache compatibility adjustments" # only if needed
```

---

## Summary of Files Changed

| File | Change |
|------|--------|
| `citationclaw/core/phase1_cache.py` | **New** — Phase1Cache class with add_papers, mark_complete, build_jsonl |
| `citationclaw/core/scraper.py` | Add `page_callback`, `year_complete_callback`, `cached_years` params (all defaulting to None) |
| `citationclaw/skills/phase1_citation_fetch.py` | Cache check, skip complete, pass callbacks, mark complete on finish |
