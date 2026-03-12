---
name: google_scholar_scraper
description: "使用 ScraperAPI 抓取 Google Scholar 的引用列表。支持断点续爬、年份遍历、多数据中心轮换和调试模式。"
metadata: '{"citationclaw":{"emoji":"🔍","requires":{"bins":[],"env":["SCRAPER_API_KEY"]},"category":"core","always":true}}'
---

# Google Scholar 爬虫 Skill

使用 ScraperAPI 抓取 Google Scholar 的引用列表，支持分页遍历和断点续爬。

## 核心功能

### 1. 抓取引用列表

```python
from citationclaw.skills.google_scholar_scraper import GoogleScholarScraper

scraper = GoogleScholarScraper(
    api_keys=["your-api-key"],
    log_callback=print,
    progress_callback=lambda c, t: print(f"{c}/{t}"),
    debug_mode=False,
    premium=False,
    ultra_premium=False,
)

await scraper.scrape(
    url="https://scholar.google.com/scholar?cites=...",
    output_file="data/output.jsonl",
    start_page=0,
    sleep_seconds=10
)
```

### 2. 支持的配置选项

| 参数 | 类型 | 说明 |
|------|------|------|
| `api_keys` | list | ScraperAPI Keys 列表 |
| `debug_mode` | bool | 调试模式（保存 HTML） |
| `premium` | bool | 启用 Premium 代理 |
| `ultra_premium` | bool | 启用 Ultra Premium 代理 |
| `session` | bool | 启用会话保持 |
| `no_filter` | bool | 追加 &filter=0 |
| `geo_rotate` | bool | 数据中心国家轮换 |
| `retry_max_attempts` | int | 最大重试次数 |
| `retry_intervals` | str | 重试间隔（如 "5,10,20"） |
| `dc_retry_max_attempts` | int | 数据中心不一致重试次数 |

### 3. 返回数据格式

每行 JSON 包含：
- `page`: 页码
- `results`: 该页结果列表
- `year`: 年份（启用年份遍历时）

### 4. 输出文件

- `citing_papers.jsonl`: 原始抓取结果
- `scraper_debug.log` (debug_mode): 详细调试日志
- `page_*.html` (debug_mode): 每页原始 HTML

## 依赖

- `requests`: HTTP 请求
- `scraperapi`: 代理服务
- 环境变量: `SCRAPER_API_KEY`

## 使用场景

1. **论文被引分析**: 抓取某篇论文的所有施引文献
2. **批量抓取**: 支持多 API Key 轮询
3. **断点续爬**: 支持从指定页码继续抓取
4. **年份遍历**: 按年份分别抓取以获得完整列表
