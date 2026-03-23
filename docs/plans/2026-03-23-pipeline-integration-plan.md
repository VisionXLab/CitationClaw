# Pipeline Integration — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Wire the new structured-API components into the actual execution pipeline so users see real changes when they click "开始分析".

**Architecture:** Create `pipeline_adapter.py` to bridge new component outputs → legacy export format. Replace the Phase 2 LLM call in `execute_for_titles()` with API-based metadata collection + scholar assessment. Replace Phase 4 LLM search with PDF-based extraction. Update frontend to show data sources, new phase steps, and pipeline architecture info.

**Tech Stack:** Existing new components (MetadataCollector, SelfCitationDetector, ScholarPreFilter, PDFDownloader, PDFCitationParser), pandas, FastAPI, Jinja2

---

## Task 1: Pipeline Adapter — Phase 1 Flattener + Legacy Format Converter

**Files:**
- Create: `citationclaw/core/pipeline_adapter.py`
- Test: `test/test_pipeline_adapter.py`

**Step 1: Write the failing test**

```python
# test/test_pipeline_adapter.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import json
import pytest
from citationclaw.core.pipeline_adapter import PipelineAdapter


def test_flatten_phase1():
    """Phase 1 nested JSONL → flat paper list."""
    adapter = PipelineAdapter()
    phase1_line = {
        "page_0": {
            "paper_dict": {
                "paper_0": {
                    "paper_link": "https://scholar.google.com/xyz",
                    "paper_title": "Test Paper A",
                    "paper_year": 2023,
                    "citation": "42",
                    "authors": {
                        "author_0_Alice Smith": "https://scholar.google.com/alice",
                        "author_1_Bob Jones": ""
                    }
                }
            }
        }
    }
    papers = adapter.flatten_phase1_line(phase1_line)
    assert len(papers) == 1
    p = papers[0]
    assert p["paper_title"] == "Test Paper A"
    assert p["paper_link"] == "https://scholar.google.com/xyz"
    assert p["paper_year"] == 2023
    assert "Alice Smith" in str(p["authors_raw"])


def test_to_legacy_record():
    """New metadata format → legacy Phase 2 output format."""
    adapter = PipelineAdapter()
    paper = {
        "paper_title": "Test Paper",
        "paper_link": "https://scholar.google.com/xyz",
        "paper_year": 2023,
        "citation": "42",
        "authors_raw": {"author_0_Alice Smith": "url1"},
    }
    metadata = {
        "title": "Test Paper",
        "authors": [
            {"name": "Alice Smith", "affiliation": "MIT", "country": "US",
             "openalex_id": "A1"},
            {"name": "Bob Jones", "affiliation": "Stanford", "country": "US",
             "openalex_id": "A2"},
        ],
        "sources": ["openalex", "s2"],
        "doi": "10.1234/test",
        "cited_by_count": 100,
        "influential_citation_count": 5,
        "pdf_url": "https://arxiv.org/pdf/2301.00001",
    }
    self_cite = {"is_self_citation": False, "method": "none"}
    scholars = [
        {"name": "Bob Jones", "tier": "Fellow", "honors": ["IEEE Fellow"],
         "affiliation": "Stanford"}
    ]
    record = adapter.to_legacy_record(
        paper=paper,
        metadata=metadata,
        self_citation=self_cite,
        renowned_scholars=scholars,
        citing_paper="Target Paper",
        record_index=1,
    )
    # Check wrapped format: {index: {fields...}}
    assert "1" in record
    inner = record["1"]
    assert inner["Paper_Title"] == "Test Paper"
    assert inner["Paper_Link"] == "https://scholar.google.com/xyz"
    assert inner["Citing_Paper"] == "Target Paper"
    assert inner["Is_Self_Citation"] == False
    assert "MIT" in inner["First_Author_Institution"]
    assert "US" in inner["First_Author_Country"]
    assert "Alice Smith" in inner["Searched Author-Affiliation"]
    assert "Bob Jones" in inner["Searched Author-Affiliation"]
    assert inner["Data_Sources"] == "openalex,s2"
    # Renowned scholar
    assert "IEEE Fellow" in str(inner["Renowned Scholar"])
    assert isinstance(inner["Formated Renowned Scholar"], list)
    assert inner["Formated Renowned Scholar"][0]["name"] == "Bob Jones"


def test_to_legacy_no_metadata():
    """When API returns None, produce minimal record."""
    adapter = PipelineAdapter()
    paper = {
        "paper_title": "Unknown Paper",
        "paper_link": "",
        "paper_year": None,
        "citation": "0",
        "authors_raw": {},
    }
    record = adapter.to_legacy_record(
        paper=paper, metadata=None,
        self_citation={"is_self_citation": False, "method": "none"},
        renowned_scholars=[], citing_paper="Target", record_index=1,
    )
    inner = record["1"]
    assert inner["Paper_Title"] == "Unknown Paper"
    assert inner["Data_Sources"] == ""
```

**Step 2: Run test → FAIL**

Run: `cd /Users/charlesyang/Desktop/CitationClaw-v2 && python -m pytest test/test_pipeline_adapter.py -v`

**Step 3: Implement PipelineAdapter**

```python
# citationclaw/core/pipeline_adapter.py
"""Bridge between new structured-API outputs and legacy export format.

Converts new Phase 2 metadata + Phase 3 scholar results into the
record format that Phase 3 Export and Phase 5 Report expect.
"""
import json
from typing import Optional, List


class PipelineAdapter:
    """Convert between new pipeline data and legacy record format."""

    def flatten_phase1_line(self, line_data: dict) -> list:
        """Flatten one Phase 1 JSONL line (page-based) into individual papers."""
        papers = []
        for page_id, page_content in line_data.items():
            paper_dict = page_content.get("paper_dict", {})
            for paper_id, paper_info in paper_dict.items():
                papers.append({
                    "page_id": page_id,
                    "paper_id": paper_id,
                    "paper_title": paper_info.get("paper_title", ""),
                    "paper_link": paper_info.get("paper_link", ""),
                    "paper_year": paper_info.get("paper_year"),
                    "citation": paper_info.get("citation", "0"),
                    "authors_raw": paper_info.get("authors", {}),
                })
        return papers

    def flatten_phase1_file(self, file_path) -> list:
        """Read Phase 1 JSONL file and flatten all pages into paper list."""
        all_papers = []
        with open(file_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                all_papers.extend(self.flatten_phase1_line(data))
        return all_papers

    def to_legacy_record(
        self,
        paper: dict,
        metadata: Optional[dict],
        self_citation: dict,
        renowned_scholars: list,
        citing_paper: str,
        record_index: int,
    ) -> dict:
        """Convert new pipeline data into legacy {index: record} format.

        This format is what Phase 3 Export expects:
          {"1": {"Paper_Title": ..., "Searched Author-Affiliation": ..., ...}}
        """
        authors = (metadata or {}).get("authors", [])
        sources = (metadata or {}).get("sources", [])

        # Build author-affiliation string (name\naffiliation pairs)
        affil_lines = []
        for a in authors:
            affil_lines.append(a.get("name", ""))
            affil_lines.append(a.get("affiliation", "") or "未知机构")
        searched_affiliation = "\n".join(affil_lines)

        # First author info
        first_author = authors[0] if authors else {}
        first_inst = first_author.get("affiliation", "")
        first_country = first_author.get("country", "")

        # Build author info summary (structured data as readable text)
        author_info_parts = []
        for a in authors:
            parts = [a.get("name", "")]
            if a.get("affiliation"):
                parts.append(f"机构: {a['affiliation']}")
            if a.get("country"):
                parts.append(f"国家: {a['country']}")
            if a.get("h_index"):
                parts.append(f"h-index: {a['h_index']}")
            author_info_parts.append(", ".join(parts))
        searched_info = "\n".join(author_info_parts)

        # Build renowned scholar fields
        renowned_text = ""
        formatted_scholars = []
        for s in renowned_scholars:
            renowned_text += f"{s.get('name', '')} ({s.get('tier', '')}: {', '.join(s.get('honors', []))})\n"
            formatted_scholars.append({
                "name": s.get("name", ""),
                "institution": s.get("affiliation", ""),
                "country": "",
                "position": s.get("tier", ""),
                "titles": ", ".join(s.get("honors", [])),
            })

        # Authors with profile (preserve original GS format for compatibility)
        authors_with_profile = json.dumps(
            paper.get("authors_raw", {}), ensure_ascii=False
        )

        record = {
            "PageID": paper.get("page_id", ""),
            "PaperID": paper.get("paper_id", ""),
            "Paper_Title": paper.get("paper_title", ""),
            "Paper_Year": paper.get("paper_year"),
            "Paper_Link": paper.get("paper_link", ""),
            "Citations": paper.get("citation", "0"),
            "Authors_with_Profile": authors_with_profile,
            "Searched Author-Affiliation": searched_affiliation,
            "First_Author_Institution": first_inst,
            "First_Author_Country": first_country,
            "Citing_Paper": citing_paper,
            "Is_Self_Citation": self_citation.get("is_self_citation", False),
            "Searched Author Information": searched_info,
            "Author Verification": "",
            "Renowned Scholar": renowned_text.strip(),
            "Formated Renowned Scholar": formatted_scholars,
            "Data_Sources": ",".join(sources),
        }
        return {str(record_index): record}
```

**Step 4: Run test → PASS**

**Step 5: Commit**

```bash
git add citationclaw/core/pipeline_adapter.py test/test_pipeline_adapter.py
git commit -m "feat: pipeline adapter bridging new API outputs to legacy export format"
```

---

## Task 2: New Phase 2+3 Integration Method in Task Executor

**Files:**
- Modify: `citationclaw/app/task_executor.py` — add `_run_new_phase2_and_3()` method, replace call in `execute_for_titles()`

**Step 1: Add new method `_run_new_phase2_and_3()`**

This method replaces the old per-paper `phase2_author_intel` call + merge + scholar assessment with:
1. Flatten Phase 1 JSONL → flat papers
2. Query MetadataCollector (OpenAlex/S2/arXiv) for each paper
3. Run SelfCitationDetector
4. Run ScholarPreFilter + ScholarSearchAgent on candidates
5. Convert all to legacy format via PipelineAdapter
6. Write merged JSONL in legacy format (ready for Phase 3 export)

Add this method to `TaskExecutor`:

```python
async def _run_new_phase2_and_3(
    self,
    citing_files: list,  # [(Path, canonical_title), ...]
    result_dir: Path,
    output_prefix: str,
    config,
    target_authors_map: dict,  # {canonical: [{name, affiliation}]}
) -> tuple:
    """New Phase 2 (API metadata) + Phase 3 (scholar assess) pipeline.

    Returns: (merged_jsonl_path, excel_path, json_path) or None on failure.
    """
    import json as _json
    from citationclaw.core.pipeline_adapter import PipelineAdapter
    from citationclaw.core.metadata_collector import MetadataCollector
    from citationclaw.core.metadata_cache import MetadataCache
    from citationclaw.core.self_citation import SelfCitationDetector
    from citationclaw.core.scholar_prefilter import ScholarPreFilter
    from citationclaw.core.scholar_search_agent import ScholarSearchAgent

    adapter = PipelineAdapter()
    metadata_cache = MetadataCache()
    collector = MetadataCollector(
        s2_api_key=getattr(config, 's2_api_key', None),
    )
    self_cite_detector = SelfCitationDetector()
    prefilter = ScholarPreFilter()

    # ── Phase 2: 作者信息采集 (structured APIs) ──
    self.log_manager.info("=" * 50)
    self.log_manager.info("Phase 2 · 作者信息采集: 通过 OpenAlex / S2 / arXiv 查询结构化数据")
    self.log_manager.info("=" * 50)

    # Flatten all Phase 1 files into papers
    all_papers = []  # [(paper_dict, canonical_title)]
    for citing_file, canonical in citing_files:
        if not citing_file.exists():
            continue
        flat = adapter.flatten_phase1_file(citing_file)
        for p in flat:
            all_papers.append((p, canonical))

    total = len(all_papers)
    if total == 0:
        self.log_manager.warning("Phase 1 未找到任何论文")
        return None
    self.log_manager.info(f"共 {total} 篇施引论文待查询")

    # Query metadata for each paper
    records = []
    record_idx = 0
    seen_dedup = set()
    all_author_dicts = []  # Collect for Phase 3

    try:
        for i, (paper, canonical) in enumerate(all_papers):
            if self.should_cancel:
                break

            title = paper["paper_title"]
            link = paper["paper_link"]

            # Dedup: (link, canonical)
            dedup_key = f"{link or title.lower()}::{canonical}"
            if dedup_key in seen_dedup:
                continue
            seen_dedup.add(dedup_key)

            # Check metadata cache
            cached = await metadata_cache.get(title=title)
            if cached:
                metadata = cached
                self.log_manager.info(f"  [{i+1}/{total}] [缓存] {title[:50]}...")
            else:
                self.log_manager.info(f"  [{i+1}/{total}] [API] {title[:50]}...")
                metadata = await collector.collect(title)
                if metadata:
                    await metadata_cache.update(
                        metadata.get("doi", ""), title, metadata
                    )

            # Self-citation check
            target_authors = target_authors_map.get(canonical, [])
            citing_authors = (metadata or {}).get("authors", [])
            self_cite = self_cite_detector.check(target_authors, citing_authors)

            # Collect authors for Phase 3
            for a in citing_authors:
                all_author_dicts.append(a)

            # Convert to legacy format (scholars filled in Phase 3)
            record_idx += 1
            record = adapter.to_legacy_record(
                paper=paper,
                metadata=metadata,
                self_citation=self_cite,
                renowned_scholars=[],  # Filled in Phase 3
                citing_paper=canonical,
                record_index=record_idx,
            )
            records.append((record, record_idx, paper, metadata, canonical))

            self.log_manager.update_progress(i + 1, total)

    finally:
        await metadata_cache.flush()
        await collector.close()

    cache_stats = metadata_cache.stats()
    self.log_manager.success(
        f"Phase 2 完成: API命中 {cache_stats['hits']} / 新查询 {cache_stats['updates']} / "
        f"共 {record_idx} 篇"
    )

    # ── Phase 3: 学者影响力评估 ──
    self.log_manager.info("=" * 50)
    self.log_manager.info("Phase 3 · 学者影响力评估: 预过滤 + 搜索候选学者")
    self.log_manager.info("=" * 50)

    # Deduplicate authors
    seen_authors = {}
    for a in all_author_dicts:
        name = a.get("name", "").strip()
        if name and name.lower() not in seen_authors:
            seen_authors[name.lower()] = a
    unique_authors = list(seen_authors.values())

    # Pre-filter
    candidates, non_candidates = prefilter.filter_candidates(unique_authors)
    self.log_manager.info(
        f"[预过滤] {len(unique_authors)} 位作者 → "
        f"{len(candidates)} 位候选, {len(non_candidates)} 位普通学者"
    )

    # Search candidates (browser search - if browser available)
    scholar_results = {}  # name → {tier, honors, ...}
    search_agent = ScholarSearchAgent()

    for idx, author in enumerate(candidates):
        if self.should_cancel:
            break
        name = author.get("name", "")
        self.log_manager.info(f"  [{idx+1}/{len(candidates)}] 搜索: {name}...")
        try:
            result = await search_agent.search(
                name=name,
                affiliation=author.get("affiliation", ""),
                h_index=author.get("h_index", 0),
                citation_count=author.get("citation_count", 0),
            )
            if result.get("tier"):
                scholar_results[name] = result
        except Exception as e:
            self.log_manager.info(f"    ⚠ {e}")

    self.log_manager.success(
        f"Phase 3 完成: {len(scholar_results)} 位知名学者 / {len(candidates)} 位候选"
    )

    # ── Rebuild records with scholar data and write merged JSONL ──
    merged_file = result_dir / "merged_authors.jsonl"
    with open(merged_file, "w", encoding="utf-8") as f:
        for record, idx, paper, metadata, canonical in records:
            # Find scholars for this paper's authors
            paper_authors = (metadata or {}).get("authors", [])
            paper_scholars = []
            for a in paper_authors:
                name = a.get("name", "")
                if name in scholar_results:
                    s = scholar_results[name]
                    paper_scholars.append({
                        "name": name,
                        "tier": s.get("tier", ""),
                        "honors": s.get("honors", []),
                        "affiliation": a.get("affiliation", ""),
                    })
            # Rebuild record with scholar data
            final_record = adapter.to_legacy_record(
                paper=paper,
                metadata=metadata,
                self_citation=self_cite_detector.check(
                    target_authors_map.get(canonical, []),
                    (metadata or {}).get("authors", []),
                ),
                renowned_scholars=paper_scholars,
                citing_paper=canonical,
                record_index=idx,
            )
            f.write(_json.dumps(final_record, ensure_ascii=False) + "\n")

    # ── Phase 3 导出 ──
    self.log_manager.info("Phase 3 · 导出结果")
    excel_file = result_dir / f"{output_prefix}_results.xlsx"
    json_file = result_dir / f"{output_prefix}_results.json"
    await self._run_skill(
        "phase3_export",
        config,
        input_file=merged_file,
        excel_output=excel_file,
        json_output=json_file,
    )

    return merged_file, excel_file, json_file
```

**Step 2: Replace old Phase 2 call in `execute_for_titles()`**

In `execute_for_titles()`, replace the entire per-paper Phase 2 loop (lines ~554-669) and merge logic (lines ~695-743) with a single call to `_run_new_phase2_and_3()`. The Phase 1 loop stays the same (it still collects citing_files). After Phase 1 finishes for all papers, call:

```python
# Replace old per-paper Phase 2 + merge + export
result = await self._run_new_phase2_and_3(
    citing_files=citing_files,
    result_dir=result_dir,
    output_prefix=output_prefix,
    config=config,
    target_authors_map={},  # Empty for now - new pipeline doesn't need LLM target authors
)
if result is None:
    return
merged_file, excel_file, json_file = result
```

**Step 3: Replace old Phase 4 call**

Replace the `phase4_citation_desc` skill call with the new `phase4_citation_extract`:

```python
if config.enable_citing_description and not _skip_phase4:
    self.log_manager.info("Phase 4 · 引文语境提取: PDF下载 + 本地解析")
    citing_desc_excel = result_dir / f"{output_prefix}_results_with_citing_desc.xlsx"
    await self._run_skill(
        "phase4_citation_extract",
        config,
        input_file=merged_file,
        output_file=result_dir / f"{output_prefix}_citing_desc.jsonl",
        target_title=canonical_titles[0] if canonical_titles else "",
        target_authors=[],
        citation_desc_cache=desc_cache,
    )
    # Merge descriptions back into Excel
    # ... (existing merge logic stays)
```

**Step 4: Run full test suite**

```bash
python -m pytest test/ -v --tb=short
```

**Step 5: Commit**

```bash
git commit -m "feat: wire new API pipeline into task executor, replacing LLM search"
```

---

## Task 3: Frontend — New Architecture UI

**Files:**
- Modify: `citationclaw/templates/index.html`
- Modify: `citationclaw/static/js/main.js`
- Modify: `citationclaw/static/css/style.css`

**Step 1: Add pipeline architecture indicator card**

Above the progress section, add a visual showing the 5 phases and data sources:

```html
<!-- Pipeline Architecture Indicator (visible during run) -->
<div id="idx-pipeline-info" style="display:none" class="agent-card mb-3">
  <div class="pipeline-phases">
    <div class="pipeline-phase" id="pp-phase1">
      <div class="pp-icon"><i class="bi bi-search"></i></div>
      <div class="pp-label">施引文献检索</div>
      <div class="pp-source">Google Scholar</div>
    </div>
    <div class="pipeline-arrow"><i class="bi bi-chevron-right"></i></div>
    <div class="pipeline-phase" id="pp-phase2">
      <div class="pp-icon"><i class="bi bi-database"></i></div>
      <div class="pp-label">作者信息采集</div>
      <div class="pp-source">OpenAlex · S2 · arXiv</div>
    </div>
    <div class="pipeline-arrow"><i class="bi bi-chevron-right"></i></div>
    <div class="pipeline-phase" id="pp-phase3">
      <div class="pp-icon"><i class="bi bi-award"></i></div>
      <div class="pp-label">学者影响力评估</div>
      <div class="pp-source">预过滤 + 浏览器搜索</div>
    </div>
    <div class="pipeline-arrow"><i class="bi bi-chevron-right"></i></div>
    <div class="pipeline-phase" id="pp-phase4">
      <div class="pp-icon"><i class="bi bi-file-pdf"></i></div>
      <div class="pp-label">引文语境提取</div>
      <div class="pp-source">PDF下载 + 本地解析</div>
    </div>
    <div class="pipeline-arrow"><i class="bi bi-chevron-right"></i></div>
    <div class="pipeline-phase" id="pp-phase5">
      <div class="pp-icon"><i class="bi bi-bar-chart"></i></div>
      <div class="pp-label">报告生成</div>
      <div class="pp-source">可视化 Dashboard</div>
    </div>
  </div>
</div>
```

**Step 2: Add CSS for pipeline phases**

```css
/* ─── Pipeline Architecture Indicator ─── */
.pipeline-phases {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 12px 0;
  overflow-x: auto;
}
.pipeline-phase {
  text-align: center;
  padding: 10px 12px;
  border-radius: 10px;
  background: var(--bg2);
  border: 1.5px solid var(--border);
  min-width: 100px;
  transition: all .3s;
}
.pipeline-phase.active {
  border-color: var(--accent);
  background: var(--accent-light);
  box-shadow: 0 0 12px rgba(37,99,235,0.15);
}
.pipeline-phase.done {
  border-color: var(--green);
  background: var(--green-light);
}
.pp-icon { font-size: 18px; margin-bottom: 4px; color: var(--muted); }
.pipeline-phase.active .pp-icon { color: var(--accent); }
.pipeline-phase.done .pp-icon { color: var(--green); }
.pp-label { font-size: 11.5px; font-weight: 600; color: var(--text); }
.pp-source { font-size: 10px; color: var(--light); margin-top: 2px; }
.pipeline-arrow { color: var(--light); font-size: 14px; }
```

**Step 3: Update JS phase detection to highlight pipeline diagram**

```javascript
// In the log message handler, detect phase transitions and update pipeline indicator
function updatePipelineIndicator(phase) {
    const phases = ['phase1','phase2','phase3','phase4','phase5'];
    const phaseMap = {
        'Phase 1': 'phase1', 'Phase 2': 'phase2',
        'Phase 3': 'phase3', 'Phase 4': 'phase4', 'Phase 5': 'phase5',
    };
    const current = phaseMap[phase];
    if (!current) return;
    const idx = phases.indexOf(current);
    phases.forEach((p, i) => {
        const el = document.getElementById('pp-' + p);
        if (!el) return;
        el.classList.remove('active', 'done');
        if (i < idx) el.classList.add('done');
        else if (i === idx) el.classList.add('active');
    });
}
```

**Step 4: Show pipeline-info card when task starts, hide when done**

In run button handler: `document.getElementById('idx-pipeline-info').style.display = ''`
In all_done handler: pipeline stays visible (shows all done)

**Step 5: Update phase detection to include new log keywords**

The new executor logs messages like:
- `"Phase 2 · 作者信息采集: 通过 OpenAlex / S2 / arXiv"` → detect Phase 2
- `"[预过滤]"` → still Phase 3
- `"Phase 4 · 引文语境提取: PDF下载"` → detect Phase 4

Update detectPhase() to match these new patterns.

**Step 6: Commit**

```bash
git commit -m "feat: frontend pipeline architecture indicator with phase highlighting"
```

---

## Task 4: Wire Phase 4 PDF-Based Extraction

**Files:**
- Modify: `citationclaw/app/task_executor.py` — replace Phase 4 call

**Step 1: Replace Phase 4 implementation**

In `execute_for_titles()`, replace the old `phase4_citation_desc` skill call with the new PDF-based flow. The new flow:

1. Read merged JSONL (records from new Phase 2+3)
2. For each paper, try to download PDF
3. Parse citation contexts from PDF
4. Use lightweight LLM to extract description from parsed text (not search)
5. Write Citing_Description back into Excel

Since the new `phase4_citation_extract` skill already does all this, we just call it differently — the input is JSONL not Excel, and the output needs to be merged back.

The key change: instead of calling old `phase4_citation_desc` with `input_excel`, call new skill with `input_file` (JSONL) and `target_title`.

**Step 2: Add merge-back logic**

After Phase 4 JSONL output, merge descriptions into the Excel file:

```python
# Read Phase 4 output JSONL and merge Citing_Description into Excel
import pandas as pd
desc_map = {}
phase4_output = result_dir / f"{output_prefix}_citing_desc.jsonl"
if phase4_output.exists():
    with open(phase4_output, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            title = rec.get("Citing_Paper_Title", rec.get("paper_title", ""))
            desc = rec.get("Citing_Description", "")
            if title and desc:
                desc_map[title.strip()] = desc
    if desc_map:
        df = pd.read_excel(excel_file)
        df["Citing_Description"] = df["Paper_Title"].str.strip().map(desc_map).fillna("")
        citing_desc_excel = result_dir / f"{output_prefix}_results_with_citing_desc.xlsx"
        df.to_excel(citing_desc_excel, index=False)
```

**Step 3: Commit**

```bash
git commit -m "feat: replace Phase 4 LLM search with PDF-based citation extraction"
```

---

## Task 5: End-to-End Smoke Test

**Files:**
- Test: `test/test_new_pipeline_e2e.py`

**Step 1: Write test**

```python
# test/test_new_pipeline_e2e.py
"""Smoke test: verify the new pipeline components are properly wired."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from citationclaw.core.pipeline_adapter import PipelineAdapter
from citationclaw.core.metadata_collector import MetadataCollector
from citationclaw.core.self_citation import SelfCitationDetector
from citationclaw.core.scholar_prefilter import ScholarPreFilter
from citationclaw.skills.phase2_metadata import MetadataCollectionSkill
from citationclaw.skills.phase3_scholar_assess import ScholarAssessSkill
from citationclaw.skills.phase4_citation_extract import CitationExtractSkill
from citationclaw.skills.registry import build_default_registry


def test_all_new_skills_registered():
    reg = build_default_registry()
    assert reg.get("phase2_metadata") is not None
    assert reg.get("phase3_scholar_assess") is not None
    assert reg.get("phase4_citation_extract") is not None


def test_adapter_full_flow():
    """Full flow: flatten → enrich → convert → export-compatible."""
    adapter = PipelineAdapter()

    # Simulate Phase 1 output
    phase1 = {
        "page_0": {
            "paper_dict": {
                "paper_0": {
                    "paper_title": "Deep Learning for NLP",
                    "paper_link": "https://scholar.google.com/abc",
                    "paper_year": 2023,
                    "citation": "10",
                    "authors": {"author_0_Alice": "url1", "author_1_Bob": "url2"}
                },
                "paper_1": {
                    "paper_title": "Transformer Models",
                    "paper_link": "https://scholar.google.com/def",
                    "paper_year": 2022,
                    "citation": "5",
                    "authors": {"author_0_Carol": "url3"}
                }
            }
        }
    }

    papers = adapter.flatten_phase1_line(phase1)
    assert len(papers) == 2

    # Simulate metadata for first paper
    metadata = {
        "title": "Deep Learning for NLP",
        "authors": [
            {"name": "Alice", "affiliation": "MIT", "country": "US"},
            {"name": "Bob", "affiliation": "Google", "country": "US"},
        ],
        "sources": ["openalex"],
        "cited_by_count": 100,
    }

    record = adapter.to_legacy_record(
        paper=papers[0],
        metadata=metadata,
        self_citation={"is_self_citation": False, "method": "none"},
        renowned_scholars=[{"name": "Bob", "tier": "Industry Leader",
                           "honors": ["Google Researcher"], "affiliation": "Google"}],
        citing_paper="My Paper",
        record_index=1,
    )

    inner = record["1"]
    # Verify all fields that Phase 3 Export needs
    assert "Paper_Title" in inner
    assert "Searched Author-Affiliation" in inner
    assert "First_Author_Institution" in inner
    assert "Renowned Scholar" in inner
    assert "Formated Renowned Scholar" in inner
    assert "Citing_Paper" in inner
    assert "Data_Sources" in inner
    assert inner["Data_Sources"] == "openalex"


def test_prefilter_integrated():
    """Verify prefilter works with real rules YAML."""
    pf = ScholarPreFilter()
    # High h-index → candidate
    assert pf.is_candidate({"name": "A", "h_index": 50, "citation_count": 0, "affiliation": ""})
    # Known institution → candidate
    assert pf.is_candidate({"name": "B", "h_index": 5, "citation_count": 0, "affiliation": "MIT"})
    # Unknown low-metric → not candidate
    assert not pf.is_candidate({"name": "C", "h_index": 5, "citation_count": 0, "affiliation": "Random U"})
```

**Step 2: Run all tests**

```bash
python -m pytest test/ -v --tb=short
```

**Step 3: Commit**

```bash
git commit -m "test: end-to-end smoke test for new pipeline integration"
```

---

## Execution Order

```
Task 1: Pipeline Adapter (format bridge)
  ↓
Task 2: Wire into task executor (core integration)
  ↓
Task 3: Frontend UI (pipeline indicator + phase highlighting)
  ↓
Task 4: Phase 4 PDF replacement
  ↓
Task 5: E2E smoke test
```
