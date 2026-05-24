<div align="right">

[English](./README.md) | 中文

</div>

<div align="center">
  <img src="docs/assets/logo.png" width="60%" alt="CitationClaw Logo"><br>

# CitationClaw v2 — 从引用洞察知识网络

让每一次引用都成为可解释的影响力<br>
<em>Turning Every Citation into Explainable Impact</em>

  [![🌐 项目主页](https://img.shields.io/badge/🌐-项目主页-blue)](https://visionxlab.github.io/CitationClaw/)
  [![PyPI](https://img.shields.io/pypi/v/citationclaw?logo=pypi&logoColor=white&color=0073b7)](https://pypi.org/project/citationclaw/)
  [![PyPI 下载量](https://img.shields.io/pypi/dm/citationclaw)](https://pypi.org/project/citationclaw)
  ![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
  ![Version](https://img.shields.io/badge/版本-2.0.0-brightgreen)
  ![Platform](https://img.shields.io/badge/平台-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey)
  ![LLM](https://img.shields.io/badge/LLM-OpenAI%20Compatible-412991?logo=openai&logoColor=white)
  ![ScraperAPI](https://img.shields.io/badge/爬取-ScraperAPI-FF6B35)
  [![License: CC BY-NC 4.0](https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey)](https://creativecommons.org/licenses/by-nc/4.0/)

**输入论文题目或 Google Scholar 学者主页，自动生成可分享的被引画像报告。**<br>
CitationClaw v2 会抓取目标论文的施引文献，采集作者与机构信息，识别院士、Fellow、国家级人才和知名机构核心成员，提取论文正文中的引用语境，并输出一份可直接在浏览器打开的 HTML 画像报告。

</div>

<div align="center">
  <video src="https://visionxlab.github.io/CitationClaw/assets/promo.mp4" poster="https://visionxlab.github.io/CitationClaw/assets/promo-poster.jpg" controls muted width="960"></video>
</div>

---

## 📢 更新日志

| 日期 | 版本 | 更新内容 |
|------|------|---------|
| 2026-05-24 | v2.0.0 | 🚀 更新 V2 文档口径：结构化元数据采集、Skills Runtime 编排、Search LLM 与轻量模型分离、PDF 引文语境提取、Basic / Advanced / Full 三档服务和可分享 HTML 报告 |
| 2026-03-18 | beta v1.0.9 | 🐛 多篇搜索去重修复、年份遍历会话行为调整、默认并发数提升至 10、缓存写入节流、UI 与日志细节优化 |
| 2026-03-12 | v1.0 | 🎉 首次公开发布：支持论文题目输入与 Google Scholar 批量导入、著名学者自动识别、HTML 画像报告、断点续爬与缓存复用 |

---

## 🚀 V2 版本定位

CitationClaw v2 不是 v1 的界面小修，而是一次面向稳定性、可解释性和可分享性的架构升级：

- 🧠 **结构化数据优先**：优先使用 OpenAlex、Semantic Scholar、arXiv、Web of Science Starter API 等结构化来源采集论文元数据和作者信息，减少完全依赖 LLM 搜索带来的不稳定。
- 🧩 **Skills Runtime + TaskExecutor 编排**：V2 注册可替换的阶段 Skill，同时由 TaskExecutor 串接更复杂的结构化元数据、PDF 校验、自引检测和学者评估主路径。
- 🔍 **Search LLM 与轻量模型分离**：需要联网检索的学者识别使用 Search LLM；报告生成和引文语境抽取可独立配置轻量模型，并可在界面中预检连通性。
- 📄 **PDF 语境提取增强**：通过 PDF 下载、缓存、解析和审查提示词，尽量从施引论文正文中定位真实引用句，并记录 PDF 来源与失败原因。
- 📊 **可分享 HTML 报告**：报告以单个 HTML 文件形式保存，包含图表、知识图谱、引用语境、AI 摘要和报告内问答入口，适合发给导师、合作者或放入汇报材料。

---

## 🔄 V1 与 V2 对比

| 维度 | V1 | V2.0.0 |
|------|----|------------|
| 执行架构 | 以脚本式流程为主，阶段耦合较高 | FastAPI + WebSocket + TaskExecutor + Skills Runtime，阶段边界更清晰 |
| 作者信息 | 更依赖 LLM 联网搜索补全 | OpenAlex / S2 / arXiv / WOS 结构化采集优先，LLM 作为补充与评估 |
| 学者识别 | 直接搜索和总结知名学者 | 先规则预过滤，再搜索核验，并结合缓存复用 |
| 引用语境 | 偏结果级摘要 | 下载和解析施引论文 PDF，提取正文引用句、章节位置和引用态度 |
| 服务层级 | 多档实验性层级，口径较分散 | 收敛为 Basic / Advanced / Full 三档，按分析深度、耗时与成本选择 |
| 报告输出 | HTML Dashboard 与 Excel 输出 | 多维 HTML 画像报告、知识图谱、引用描述综合分析、费用摘要和报告内助手 |
| 成本控制 | 依赖手动估算 | 支持缓存复用、Basic 关闭 Phase 4、LLM 额度追踪、年份遍历提示和从缓存重建报告 |
| 可维护性 | 适合快速迭代 | 更适合长期维护、单元测试和替换外部服务 |

---

## 📈 V1 vs V2 评测对比

基于人工标注 Ground Truth 的施引论文样本，从五个维度对 v1 与 v2 进行定量评测。总分为加权求和（Author 25%、Scholar 15%、PDF 15%、Citation 35%、Data Source 10%）。

| 维度 | v1 | v2 | 提升 | 衡量内容 |
|------|:--:|:--:|:---:|---------|
| **Author** | 75.51 | **87.02** | +11.51 | 作者姓名匹配 (F1)、机构准确率与已知率 |
| **Scholar** | 73.55 | **78.57** | +5.02 | 是否识别出 GT 中标注的院士 / Fellow 等知名学者 |
| **PDF** | 0 | **74.43** | +74.43 | 施引论文 PDF 成功下载并可解析的比例 |
| **Citation** | 13.81 | **46.26** | +32.45 | 提取的引文原句与 GT 引文句的语义相似度（LLM 评判） |
| **Data Source** | 75.92 | **80.82** | +4.90 | 元数据来源完整性与正确性（机构覆盖率、错误论文比例） |
| **Overall** | 42.33 | **68.98** | **+26.65** | 五维加权综合得分 |

**结果分析：**
- **Citation（+32.45）** 提升最为显著 — v1 输出偏向解释性摘要，难以与 GT 引文句对齐；v2 从 PDF 正文中提取实际引用句，语义匹配度大幅提升。
- **Author（+11.51）** 得益于结构化 API（OpenAlex / S2 / WOS）替代纯 LLM 提取，配合 PDF 回退补全缺失机构。
- **Scholar（+5.02）** 通过规则预过滤 + 缓存复用减少漏识别。
- **PDF（+74.43）** — v1 无 PDF 下载与解析能力；v2 新增 12 级下载级联、ScraperAPI 出版商通道和 LLM 搜索兜底。

> [!IMPORTANT]
> **成本优势**：v2 的 LLM Token 消耗量仅为 v1 的约 **1/5**，同时在所有维度上取得更高分数。

---

## 🧭 快速导览

| 文档 | 说明 |
|------|------|
| [📘 完整指南（Guidelines）](https://visionxlab.github.io/CitationClaw/guidelines.html) | 安装、Quick Start、配置、输出、FAQ 与运行建议 |
| [📊 画像报告示例 1](https://visionxlab.github.io/CitationClaw/demo1.html) | 在线预览一份真实输出样例 |
| [📊 画像报告示例 2](https://visionxlab.github.io/CitationClaw/demo2.html) | 另一份真实论文的被引画像报告 |

---

## 📦 安装

需要 **Python 3.10 及以上版本**，推荐 Python 3.12。

### 方式一：pip 安装

```bash
pip install citationclaw
citationclaw
citationclaw --port 8080
```

启动后浏览器会打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)，或你指定的端口。

### 方式二：源码运行

```bash
git clone https://github.com/VisionXLab/CitationClaw.git
cd CitationClaw
pip install -r requirements.txt
python -m citationclaw
```

---

## 🧩 五阶段流水线

```text
Phase 0  引用入口查找
Phase 1  施引文献检索：Google Scholar + ScraperAPI
Phase 2  作者与元数据采集：OpenAlex / Semantic Scholar / arXiv / WOS / PDF
Phase 3  学者影响力评估：预过滤 + Search LLM + 缓存
Phase 4  引文语境提取：PDF 下载解析 + 轻量 LLM 抽取与审查
Phase 5  报告生成：Excel / JSON / HTML Dashboard
```

SkillsRuntime 注册了 `phase1_citation_fetch`、`phase2_metadata`、`phase3_scholar_assess`、`phase4_citation_extract` 和 `phase5_report_generate` 等阶段 Skill。当前完整运行路径仍由 `TaskExecutor._run_new_phase2_and_3()` 承担结构化元数据、PDF 校验、自引检测和学者评估这一整块主流程。

---

## ⚙️ 服务层级

| 层级 | 适用场景 | 主要行为 |
|------|----------|----------|
| Basic | 首次试跑、成本敏感、只想知道是否有重量级学者引用 | 抓取施引文献，采集作者信息，评估知名学者，不做引文语境分析 |
| Advanced | 需要了解重要施引论文如何讨论目标论文 | 开启引文语境提取，生成更深入的引用画像 |
| Full | 基金、述职、项目汇报前需要完整引用画像 | 对全部施引论文执行引用语境提取，生成最完整报告，成本最高 |

引用量超过 1000 的论文建议开启「按年份遍历」，系统会按年份分段抓取以绕过 Google Scholar 单次最多显示 1000 条结果的限制。
更多服务层级细节和当前实现说明请查看 [完整指南（Guidelines）](https://visionxlab.github.io/CitationClaw/guidelines.html)。

---

## 📤 输出与分享

每次运行会在 `data/result-{时间戳}/` 中生成结果文件，常见产物包括：

- `paper_results.xlsx`：全部施引论文、作者、机构、引用量和基础评估结果。
- `paper_results_all_renowned_scholar.xlsx`：所有被识别出的知名学者引用汇总。
- `paper_results_top-tier_scholar.xlsx`：顶尖学者子集。
- `paper_results_with_citing_desc.xlsx`：包含引用原句、章节位置和态度标注的增强表格。
- `paper_results.json`：便于程序继续处理的结构化数据。
- `paper_dashboard.html`：可直接分享的 HTML 被引画像报告。

`paper_dashboard.html` 是核心分享产物。它是一个自包含网页文件，可用浏览器直接打开，适合发送给导师、合作者、评审材料撰写者，或作为基金申请、述职汇报、成果总结中的可视化佐证。报告中的下载按钮和 AI 问答能力在 CitationClaw 本地服务中体验最完整；离线分享时，图表与正文内容仍可阅读。

如果本地已经存在作者信息和引文描述缓存，也可以从缓存快速重建报告，避免重复执行完整抓取与抽取流程。

---

## 🔧 配置要点

- **ScraperAPI Keys**：用于抓取 Google Scholar 引用列表。建议配置多个 Key 轮换，提高稳定性。
- **Search LLM**：用于学者影响力搜索与事实核验，必须具备 web search 能力。
- **轻量模型**：用于报告生成与引文语境抽取，可与 Search LLM 使用不同服务商。
- **Semantic Scholar API Key**：可选，能提升结构化元数据和 PDF 链接获取稳定性。
- **Web of Science Starter API Key**：可选，用于更高优先级的结构化作者提取。
- **MinerU API Token**：可选，用于大文件或复杂 PDF 的高质量解析。
- **CDP 端口**：可选，连接已登录的 Chrome/Edge 会话，用于 IEEE、Elsevier、ACM 等需要权限的下载场景。
- **费用追踪**：配置 API 中转站系统令牌和用户 ID 后，运行结束会估算 LLM 额度消耗。
- **模型预检**：界面可在正式运行前测试 Search LLM 与轻量模型是否可用。

---

## ❓ 常见问题

**为什么 V2 仍然需要 Search LLM？**
结构化 API 可以稳定提供论文、作者和机构基础信息，但院士、Fellow、国家级人才、企业研究负责人等身份需要跨网页核验。Search LLM 用于补充这部分信息，并由规则和缓存降低重复成本。

**作者信息出现错误或幻觉怎么办？**
优先检查 Search LLM 是否真的支持联网搜索；其次开启作者信息真实性校验；重要结论应人工复核原始链接、Google Scholar 主页、大学主页或官方 Fellow/院士名单。

**引用描述是否一定准确？**
CitationClaw 会尽量从 PDF 正文中定位引用目标论文的原句，并使用审查提示词过滤明显错误，但 PDF 解析和 LLM 抽取仍可能失败。正式使用前建议核对报告中的原文和来源论文。

**HTML 报告为什么没有引文描述分析？**
如果选择 Basic，Phase 4 不会执行，报告会跳过引文描述部分。需要该部分时请选择 Advanced 或 Full 后重新运行。

---

## 🌍 社区与动态

CitationClaw 面向科研人员、研究团队、项目管理者和希望理解成果影响力的人群。更完整的平台化版本将在 [减论 reduct.cn](https://www.reduct.cn/) 上线，提供更稳定的任务管理和服务化体验。

欢迎扫码加入用户交流群，获取最新动态、交流使用心得。如二维码过期，请添加个人微信邀请进群：

<div align="center">
  <img src="docs/assets/group.jpg" width="200" alt="用户交流群二维码">
  &nbsp;&nbsp;&nbsp;&nbsp;
  <img src="docs/assets/personal_wc.jpg" width="200" alt="个人微信二维码">
</div>

---

## ⚠️ 免责声明

本项目仅供学术研究和个人学习使用。请遵守 Google Scholar、ScraperAPI、OpenAlex、Semantic Scholar、arXiv、Web of Science、MinerU 以及所选 LLM 服务商的服务条款和当地法律法规。CitationClaw 输出的作者身份、引用语境和影响力分析应作为辅助材料，正式使用前需要人工核验。作者不对使用本工具产生的任何后果负责。

---

## ⭐ Star 趋势

<div align="center">

[![Star History Chart](https://api.star-history.com/svg?repos=VisionXLab/CitationClaw&type=Date)](https://star-history.com/#VisionXLab/CitationClaw&Date)

</div>

## 👥 开发者团队

**上海交通大学 VisionXLab@RethinkLab**<br>
杨起豪 (Qihao Yang)、张春浩 (Chunhao Zhang)、龚子洋 (Ziyang Gong)、樊子谦 (Ziqian Fan)、周奕帆 (Yifan Zhou)、周越 (Yue Zhou)、钟志航 (Zhihang Zhong)、杨学 (Xue Yang)<sup><b>⭐ Project Leader</b></sup>

**华东师范大学 & 上海人工智能实验室 DMCV**<br>
程依凡 (Yifan Cheng)、许张涵 (Zhanghan Xu)、陆佳炜 (Jiawei Lu)、谭鑫 (Xin Tan)

**东南大学 PALM 实验室**<br>
李操瑞 (Caorui Li)、周天一 (Tianyi Zhou)、杨旭 (Xu Yang)

> [!NOTE]
> **致谢**：特别感谢 **陈柯宇 (Keyu Chen)** 对本项目算力与 API 资源的慷慨赞助，使本项目的开发与运行成为可能。

---

## 📚 如何引用

如果 CitationClaw 对你的研究、汇报或项目分析有帮助，欢迎引用本项目：

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
