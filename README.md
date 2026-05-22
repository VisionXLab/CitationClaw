<div align="right">

English | [中文](./README.zh-CN.md)

</div>

<div align="center">
  <img src="docs/assets/logo.png" width="60%" alt="CitationClaw Logo"><br>

# CitationClaw v2: Turning Every Citation into Explainable Impact

让每一次引用都成为可解释的影响力<br>
<em>A citation portrait engine for discovering, explaining, and sharing scientific impact.</em>

[![Homepage](https://img.shields.io/badge/Homepage-CitationClaw-blue)](https://visionxlab.github.io/CitationClaw/)
[![PyPI](https://img.shields.io/pypi/v/citationclaw?logo=pypi&logoColor=white&color=0073b7)](https://pypi.org/project/citationclaw/)
[![PyPI Downloads](https://img.shields.io/pypi/dm/citationclaw)](https://pypi.org/project/citationclaw/)
[![Visitors](https://visitor-badge.laobi.icu/badge?page_id=VisionXLab.CitationClaw)](https://github.com/VisionXLab/CitationClaw)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=flat-square)](https://github.com/VisionXLab/CitationClaw/pulls)
[![Issues](https://img.shields.io/github/issues/VisionXLab/CitationClaw)](https://github.com/VisionXLab/CitationClaw/issues)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Version](https://img.shields.io/badge/version-2.0.0-brightgreen)
![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey)
![LLM](https://img.shields.io/badge/LLM-OpenAI%20Compatible-412991?logo=openai&logoColor=white)
![ScraperAPI](https://img.shields.io/badge/Crawler-ScraperAPI-FF6B35)
[![License: CC BY-NC 4.0](https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey)](https://creativecommons.org/licenses/by-nc/4.0/)

**Input a paper title or a Google Scholar profile, then generate a shareable citation portrait report.**<br>
CitationClaw v2 crawls citing papers, collects author and institution metadata, identifies renowned scholars, extracts in-paper citation contexts, and produces a self-contained HTML report for research summaries, grant materials, and academic presentations.

</div>

---

## 📢 News

- **2026-05-22**: Released **v2.0.0** documentation — structured metadata collection, Skills Runtime orchestration, separated search/lightweight model roles, PDF-grounded citation contexts, Basic / Advanced / Full service tiers, and shareable HTML reports.
- **2026-03-18**: Released **beta v1.0.9** — multi-paper dashboard dedup fix, year-traverse session behavior update, default parallel workers raised to 10, cache write throttling, and UI/logging polish.
- **2026-03-12**: Released **v1.0** — first public release.

---

## 🚀 What v2 Changes

CitationClaw v2 is an architectural upgrade over v1, not just a UI refresh.

- 🧠 **Structured metadata first**: OpenAlex, Semantic Scholar, arXiv, Web of Science Starter API, and PDF-based fallbacks reduce the instability of fully LLM-driven author lookup.
- 🧩 **Skills Runtime + TaskExecutor orchestration**: v2 registers replaceable phase skills under SkillsRuntime, while TaskExecutor coordinates the richer structured-metadata, PDF-validation, self-citation, and scholar-assessment path.
- 🔍 **Separated model roles**: search-capable LLMs handle scholar verification; cheaper lightweight models can handle report generation and citation-context extraction, with preflight checks in the UI.
- 📄 **PDF-grounded citation context**: v2 downloads, caches, parses, and reviews citing PDFs to recover actual citation sentences where possible, while recording PDF sources and failure reasons.
- 📊 **Shareable HTML report**: the final dashboard is a single browser-readable file with charts, knowledge graph, citation descriptions, cost summary, and a report assistant entry point.

## 🔄 v1 vs v2

| Area | v1 | v2.0.0 |
|------|----|------------|
| Execution model | Script-oriented flow with tighter coupling | FastAPI + WebSocket + TaskExecutor + Skills Runtime |
| Author data | Heavier dependence on LLM web search | Structured APIs first, LLM search as supplement and assessor |
| Scholar detection | Direct search and summarization | Rule pre-filtering, cached lookup, search verification |
| Citation context | Result-level summaries | PDF download/parse/review pipeline for in-text citation sentences |
| Service tiers | Multiple experimental modes | Three-tier config: Basic / Advanced / Full for balancing depth, runtime, and cost |
| Report | HTML dashboard and spreadsheets | Self-contained citation portrait with graph, citation-context analysis, cost summary, and assistant |
| Cost control | Mostly manual estimation | Cache reuse, Basic Phase 4 disable switch, quota check, year-traverse prompt, and report rebuild from cache |
| Maintainability | Good for fast iteration | Better phase contracts, isolated skills, and testable module boundaries |

## 🧭 Quick Links

| Resource | Description |
|----------|-------------|
| [📘 Guidelines](https://visionxlab.github.io/CitationClaw/guidelines.html) | Installation, quick start, configuration, outputs, FAQ, and operation notes |
| [📊 Report Demo 1](https://visionxlab.github.io/CitationClaw/demo1.html) | Online preview of a generated citation portrait |
| [📊 Report Demo 2](https://visionxlab.github.io/CitationClaw/demo2.html) | Another generated report example |

## 📦 Install

Requires **Python 3.10+**. Python 3.12 is recommended.

### PyPI

```bash
pip install citationclaw
citationclaw
citationclaw --port 8080
```

The app opens at [http://127.0.0.1:8000](http://127.0.0.1:8000), or the port you specify.

### Source

```bash
git clone https://github.com/VisionXLab/CitationClaw.git
cd CitationClaw
pip install -r requirements.txt
python -m citationclaw
```

## 🧩 Five-Phase Pipeline

```text
Phase 0  Citation entry discovery
Phase 1  Citing-paper retrieval: Google Scholar + ScraperAPI
Phase 2  Author and metadata collection: OpenAlex / S2 / arXiv / WOS / PDF
Phase 3  Scholar impact assessment: pre-filter + Search LLM + cache
Phase 4  Citation-context extraction: PDF parse + lightweight LLM + review
Phase 5  Report generation: Excel / JSON / HTML dashboard
```

SkillsRuntime registers phase skills such as `phase1_citation_fetch`, `phase2_metadata`, `phase3_scholar_assess`, `phase4_citation_extract`, and `phase5_report_generate`. The current full-run path still uses `TaskExecutor._run_new_phase2_and_3()` for the combined structured metadata, PDF validation, self-citation, and scholar-assessment block.

## ⚙️ Service Tiers

| Tier | Best for | Behavior |
|------|----------|----------|
| Basic | First runs, cost-sensitive checks, scholar-only impact scans | Retrieves citing papers, collects author metadata, assesses renowned scholars, skips citation-context extraction |
| Advanced | Understanding how important citing papers discuss a work | Enables citation-context extraction for a deeper portrait of important citing work |
| Full | Grant writing, evaluation, presentations, and complete citation portraits | Runs citation-context extraction for all citing papers; highest cost and longest runtime |

For papers with more than 1000 citations, enable year traversal. It splits Google Scholar queries by year to work around the 1000-result display limit.
See the [Guidelines](https://visionxlab.github.io/CitationClaw/guidelines.html) for detailed tier behavior and current implementation notes.

## 📤 Outputs and Sharing

Each run creates a timestamped folder under `data/result-{timestamp}/`, usually including:

- `paper_results.xlsx`
- `paper_results_all_renowned_scholar.xlsx`
- `paper_results_top-tier_scholar.xlsx`
- `paper_results_with_citing_desc.xlsx`
- `paper_results.json`
- `paper_dashboard.html`

`paper_dashboard.html` is the main shareable artifact. It is a self-contained browser-readable report that can be sent to advisors, collaborators, or evaluators, and can be reused in grant applications, annual reviews, and presentation preparation. Download buttons and AI assistant features work best when the report is opened from the local CitationClaw app; the static charts and report content remain readable when shared offline.

If author and citation-description caches already exist, the app can rebuild a report from cache without repeating the full crawl and extraction workflow.

## 🔧 Configuration Highlights

- **ScraperAPI Keys**: required for Google Scholar crawling; multiple keys improve stability.
- **Search LLM**: required for scholar assessment and verification; must support web search.
- **Lightweight model**: optional independent model endpoint for report generation and citation-context extraction.
- **Semantic Scholar API Key**: optional but improves metadata and PDF discovery.
- **Web of Science Starter API Key**: optional higher-priority structured author extraction.
- **MinerU API Token**: optional parser for larger or more complex PDFs.
- **CDP debug port**: optional Chrome/Edge session for authenticated IEEE, Elsevier, and ACM downloads.
- **Quota tracking**: optional API relay token/user ID pair for estimating LLM quota consumption after each run.
- **Model preflight**: the UI can test Search LLM and lightweight model connectivity before a full run.

## 📁 Project Structure

```text
citationclaw/
├── app/                 # FastAPI app, task orchestration, config, logs
├── core/                # scraping, metadata, PDF, export, dashboard engines
├── skills/              # Skills Runtime and phase skills
├── static/              # frontend assets
├── templates/           # Jinja2 pages
docs/                    # documentation site and demos
test/                    # tests
```

## 🌍 Community

- Product update: [减论 reduct.cn](https://www.reduct.cn/)
- User group in China:

<div align="center">
  <img src="docs/assets/group.jpg" width="200" alt="User Group QR">
</div>

## ⚠️ Disclaimer

CitationClaw is intended for academic research and personal study. Follow the terms of Google Scholar, ScraperAPI, OpenAlex, Semantic Scholar, arXiv, Web of Science, MinerU, and your selected LLM provider. Author identities, citation contexts, and impact analysis should be treated as assistive outputs and manually verified before formal use. The authors are not responsible for consequences arising from use of this tool.

## ⭐ Star History

<div align="center">

[![Star History Chart](https://api.star-history.com/svg?repos=VisionXLab/CitationClaw&type=Date)](https://star-history.com/#VisionXLab/CitationClaw&Date)

</div>

## 👥 Team

**Shanghai Jiao Tong University — VisionXLab@RethinkLab**<br>
Qihao Yang (杨起豪), Chunhao Zhang (张春浩), Ziyang Gong (龚子洋), Ziqian Fan (樊子谦), Yifan Zhou (周奕帆), Yue Zhou (周越), Zhihang Zhong (钟志航), Xue Yang (杨学)<sup><b>⭐ Project Leader</b></sup>

**East China Normal University & Shanghai AI Lab — DMCV**<br>
Yifan Cheng (程依凡), Zhanghan Xu (许张涵), Jiawei Lu (陆佳炜), Xin Tan (谭鑫)

**Southeast University — PALM Lab**<br>
Caorui Li (李操瑞), Tianyi Zhou (周天一), Xu Yang (杨旭)

> [!NOTE]
> **Acknowledgment**: Special thanks to **Keyu Chen (陈柯宇)** for generously sponsoring the compute and API resources that made this project possible.

## 📚 Citation

If CitationClaw helps your research, reporting, or evaluation workflow, please cite the project:

```bibtex
@software{citationclaw2026,
  title        = {CitationClaw: Turning Every Citation into Explainable Impact},
  author       = {Yang, Qihao and Zhang, Chunhao and Cheng, Yifan and Gong, Ziyang and Li, Caorui and Xu, Zhanghan and Zhou, Tianyi and Lu, Jiawei and Fan, Ziqian and Zhou, Yifan and Zhou, Yue and Zhong, Zhihang and Yang, Xu and Tan, Xin and Yang, Xue},
  year         = {2026},
  version      = {2.0.0},
  url          = {https://github.com/VisionXLab/CitationClaw},
  institution  = {Shanghai Jiao Tong University, East China Normal University, Southeast University}
}
```
