# 论文被引画像分析智能体

输入论文题目，智能体自动检索引用关系、搜索学者画像，并生成多维 HTML 分析报告。支持多篇论文同时分析。

---

## Quick Start

```bash
pip install -r requirements.txt
python start.py
```

打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)，在首页输入论文题目，配置 API，点击**开始分析**即可。

---

## 功能特性

- **直接输入题目**：在首页文本框中每行填写一篇论文题目，支持多篇同时分析
- **全自动流水线**：URL 查找 → 爬取引用列表 → 学者信息搜索 → 数据导出，全程无需手动干预
- **著名学者筛选**：自动识别院士、Fellow、杰青等重量级学者，生成专项 Excel
- **作者信息校验**（可选）：通过搜索 API 对学者信息进行独立核验
- **引用描述搜索**（Phase 4，可选）：为每篇施引文献检索其引用该论文的具体描述
- **画像报告生成**（Phase 5，可选）：生成单文件自包含 HTML 分析报告，包含：
  - 引用年份分布、学者层级分布、国家/地区分布
  - 关键词云（含中文翻译）
  - 情感倾向与引用深度分析
  - 著名学者画像一览（可展开引用描述，支持 Markdown 渲染）
  - 高影响力引用论文详情（含作者主页链接）
  - 引用趋势预测（LLM + 线性回归双路径）
- **实时日志**：WebSocket 推送任务进度和日志，支持随时取消
- **统一输出目录**：每次运行结果集中存放于 `data/result-{时间戳}/`

---

## 安装

### 1. 安装 Python 依赖

```bash
pip install -r requirements.txt
```


---

## 使用流程

### Step 1：启动系统

```bash
python start.py
```

启动后自动打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)。

### Step 2：输入论文题目

在首页的文本框中，每行填写一篇目标论文的完整英文题目：

```
Attention Is All You Need
A Survey on Visual Foundation Models
```

### Step 3：配置 API（首次使用）

展开页面上的 **API 配置** 折叠栏，填写：

| 字段 | 说明 |
|------|------|
| ScraperAPI Key(s) | [scraperapi.com](https://dashboard.scraperapi.com) 的密钥，多个用英文逗号分隔，建议 3 个以上轮换 |
| OpenAI 兼容 API Key | 支持 OpenAI 格式的 API 密钥 |
| Base URL | API 的 Base URL，默认 `https://api.gpt.ge/v1/` |
| Search Model | 用于学者信息搜索的模型，**必须具备 web search 能力**，推荐 `gemini-3-flash-preview-search` |
| 输出文件前缀 | 输出文件名前缀，默认 `paper` |

**可选功能开关**（同在配置栏中）：

| 开关 | 说明 |
|------|------|
| 启用著名学者筛选 | 从搜索结果中识别重量级学者，生成专项 Excel |
| 启用作者信息验证 | 通过搜索 API 对学者信息进行独立核验（耗时较长） |
| 启用引用描述搜索 | Phase 4，为每篇施引文献搜索引用描述文字 |
| 启用画像报告生成 | Phase 5，生成 HTML 分析报告，**需先启用著名学者筛选** |
| 画像报告模型 | Phase 5 专用的 LLM 模型，推荐非 search 类模型，如 `gemini-3-flash-preview-nothinking` |

点击**保存配置**后，点击**开始分析**。

### Step 4：等待执行

页面显示实时日志和进度条。任务自动依次执行以下阶段：

| 阶段 | 描述 | 输出 |
|------|------|------|
| Phase 1 | 通过 ScraperAPI 爬取 Google Scholar 引用列表 | `*_citing.jsonl` |
| Phase 2 | 调用搜索 API 获取每篇施引文献的作者信息、机构、学术头衔 | `*_authors.jsonl` |
| Phase 3 | 合并数据，导出 Excel 和 JSON | `*_results.xlsx`, `*_results.json` |
| Phase 4 | （可选）为每篇施引文献搜索引用描述 | `*_results_with_citing_desc.xlsx` |
| Phase 5 | （可选）LLM 生成多维 HTML 画像报告 | `*_dashboard.html` |

任务完成后，页面显示所有可下载的结果文件链接。

---

## 输出文件

所有文件统一保存在 `data/result-{时间戳}/` 目录下：

| 文件 | 说明 |
|------|------|
| `*_results.xlsx` | 完整结果（论文信息 + 作者信息），含著名学者高亮和专项 Sheet |
| `*_results_with_citing_desc.xlsx` | 含引用描述的增强版 Excel（Phase 4 输出） |
| `*_results.json` | JSON 格式结构化数据 |
| `*_dashboard.html` | 单文件自包含 HTML 画像报告（Phase 5 输出） |
| `*_all_renowned_scholar.xlsx` | 所有著名学者汇总 |
| `*_top-tier_scholar.xlsx` | 顶尖学者（院士/Fellow）专项列表 |

---

## 独立生成画像报告

如果已有结果 Excel，可以跳过爬取步骤，直接用 `core/dashboard_test.py` 生成 HTML 报告：

```bash
# 最简用法：自动推断同目录下的配套文件
python core/dashboard_test.py data/result-20260225/paper_results.xlsx

# 完整指定所有路径和参数
python core/dashboard_test.py data/result-20260225/paper_results.xlsx \
    --renowned-all data/result-20260225/paper_results_all_renowned_scholar.xlsx \
    --renowned-top data/result-20260225/paper_results_top-tier_scholar.xlsx \
    --output       my_report.html \
    --api-key      sk-xxxx \
    --base-url     https://api.gpt.ge/v1/ \
    --model        gemini-3-flash-preview-nothinking

# 跳过确认提示直接执行
python core/dashboard_test.py data/result-20260225/paper_results.xlsx --yes
```

未指定的参数会自动从 `config.json` 读取；配套学者文件未指定时会在同目录下按命名规范自动搜索。

---

## 配置说明

配置通过 Web 界面保存，也可直接编辑项目根目录的 `config.json`：

```json
{
  "scraper_api_keys": ["key1", "key2", "key3"],
  "openai_api_key": "sk-...",
  "openai_base_url": "https://api.gpt.ge/v1/",
  "openai_model": "gemini-3-flash-preview-search",
  "default_output_prefix": "paper",
  "sleep_between_pages": 10,
  "sleep_between_authors": 0.5,
  "parallel_author_search": 5,
  "resume_page_count": 0,
  "enable_renowned_scholar_filter": true,
  "enable_author_verification": false,
  "author_verify_model": "gemini-3-pro-preview-search",
  "enable_citing_description": true,
  "enable_dashboard": true,
  "dashboard_model": "gemini-3-flash-preview-nothinking"
}
```

**主要配置项说明**：

| 字段 | 说明 |
|------|------|
| `scraper_api_keys` | ScraperAPI 密钥数组，多个密钥轮换使用 |
| `openai_model` | **必须为带 web search 能力的模型** |
| `parallel_author_search` | Phase 2 并发搜索数，默认 5 |
| `sleep_between_pages` | 爬取页面间的等待秒数，默认 10 |
| `resume_page_count` | 断点续爬起始页，0 为从头开始 |
| `enable_renowned_scholar_filter` | 启用著名学者筛选（Phase 5 依赖此项） |
| `dashboard_model` | Phase 5 使用的模型，推荐非 search 类以节省费用 |

---

## 常见问题

**ScraperAPI 请求失败**
- 检查 API Key 是否正确、额度是否充足
- 多个 Key 轮换可有效提高稳定性
- 任务失败时可通过 `resume_page_count` 设置起始页断点续爬

**作者信息质量差 / 出现幻觉**
- 搜索模型**必须具备实时 web search 能力**，否则 LLM 会编造信息
- 推荐使用 `gemini-3-flash-preview-search` 或同等带搜索能力的模型

**Phase 5 画像报告未生成**
- 需先勾选"启用著名学者筛选"，Phase 5 依赖著名学者数据
- 检查 `dashboard_model` 配置是否正确

**Playwright 浏览器启动失败**
```bash
python -m playwright install chromium
```

**任务中断后续爬**
- 在配置页面（或 `config.json`）将 `resume_page_count` 设置为中断的页码，重新开始任务

---

## 项目结构

```
project_root/
├── start.py                        # 启动入口
├── config.json                     # 配置文件（首次运行自动创建）
├── requirements.txt
│
├── app/                            # Web 应用层
│   ├── main.py                     # FastAPI 主应用 & API 路由
│   ├── config_manager.py           # 配置读写（AppConfig Pydantic 模型）
│   ├── task_executor.py            # 流水线编排（Phase 1-5）
│   ├── browser_controller.py       # Playwright 浏览器控制
│   └── log_manager.py              # WebSocket 日志推送
│
├── core/                           # 核心业务逻辑
│   ├── scraper.py                  # Phase 1：Google Scholar 爬虫（async）
│   ├── author_searcher.py          # Phase 2：学者信息搜索（async）
│   ├── exporter.py                 # Phase 3：Excel/JSON 导出（sync）
│   ├── citing_description_searcher.py  # Phase 4：引用描述搜索（async）
│   ├── dashboard_generator.py      # Phase 5：HTML 画像报告生成（sync）
│   ├── dashboard_test.py           # 独立运行 Phase 5 的命令行工具
│   ├── url_finder.py               # 论文引用列表 URL 查找
│   └── parser.py                   # Google Scholar HTML 解析
│
├── templates/                      # Jinja2 HTML 模板
│   ├── base.html
│   ├── index.html                  # 主页（输入题目 + 配置 + 实时日志）
│   ├── config.html
│   └── results.html
│
├── static/
│   ├── css/
│   └── js/
│       ├── websocket.js            # WebSocket 管理
│       └── main.js                 # 前端逻辑
│
└── data/
    └── result-{时间戳}/            # 每次运行的独立输出目录
        ├── *_results.xlsx
        ├── *_results_with_citing_desc.xlsx
        ├── *_results.json
        ├── *_dashboard.html
        ├── *_all_renowned_scholar.xlsx
        └── *_top-tier_scholar.xlsx
```

---

## 技术栈

| 层次 | 技术 |
|------|------|
| 后端框架 | FastAPI + Uvicorn |
| 实时通信 | WebSocket |
| 浏览器自动化 | Playwright (Chromium) |
| 数据处理 | Pandas + OpenPyXL |
| LLM 调用 | OpenAI SDK（兼容任意 OpenAI 格式 API） |
| 前端 | Bootstrap 5 + Chart.js 4 + marked.js |
| 报告渲染 | 单文件自包含 HTML（无需服务端） |

---

## 免责声明

本项目仅供学术研究和个人学习使用。请遵守 Google Scholar 服务条款及当地法律法规，避免高频抓取。作者不对使用本工具产生的任何后果负责。

---

**开发者**：Qihao Yang, Ziqian Fan, Xue Yang (Project Leader)
**版本**：2.0
**更新日期**：2026-02-25
