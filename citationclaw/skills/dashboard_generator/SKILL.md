---
name: dashboard_generator
description: "基于抓取和分析结果生成精美的 HTML 可视化画像报告。包含引用趋势、学者分布、机构统计、词云等。"
metadata: '{"citationclaw":{"emoji":"📊","requires":{"bins":[],"env":["OPENAI_API_KEY"]},"category":"core","always":false}}'
---

# HTML 报告生成 Skill

基于已抓取的引用数据和作者分析结果，生成精美可视化 HTML 画像报告。

## 核心功能

### 1. 生成画像报告

```python
from citationclaw.skills.dashboard_generator import DashboardGenerator

generator = DashboardGenerator(
    api_key="your-api-key",
    base_url="https://api.gpt.ge/v1/",
    model="gemini-3-flash-preview-nothinking",
    log_callback=print,
    test_mode=False
)

await generator.generate(
    merged_jsonl_file="data/merged_results.jsonl",
    dashboard_file="data/paper_dashboard.html",
    target_paper_info={
        "title": "论文标题",
        "authors": "作者1, 作者2",
        "year": 2023,
        "venue": "Conference/Journal",
        "citation_count": 100
    },
    config=config_dict
)
```

### 2. 报告内容

- **论文概览**: 被引论文的基本信息和引用趋势
- **引用分布**: 年度引用柱状图、月度趋势折线图
- **学者画像**: 
  - 知名学者列表（院士/Fellow/企业大佬）
  - 学者机构分布（全球地图可视化）
  - 学者类型统计（学术界/工业界比例）
- **机构分析**: 顶尖高校、科技企业分布
- **引用质量**: 引用描述分析、自引检测
- **词云可视化**: 引用论文标题关键词

### 3. 支持的配置选项

| 参数 | 类型 | 说明 |
|------|------|------|
| `api_key` | str | LLM API Key |
| `base_url` | str | API Base URL |
| `model` | str | 报告生成模型 |
| `skip_citing_analysis` | bool | 跳过引用描述分析 |
| `specified_scholars` | str | 指定关注的学者 |

### 4. 知名机构识别

自动识别并分类以下类型机构：

**国际科技企业**: Google, DeepMind, OpenAI, Meta, Microsoft Research, NVIDIA, Anthropic, Apple, Amazon, IBM Research, Samsung Research, Adobe Research, Qualcomm

**国内科技企业**: 华为, 阿里巴巴/达摩院, 字节跳动, 腾讯, 百度, 商汤科技, 旷视科技, 小米, 京东, 美团, 快手, 网易, 平安科技, 蚂蚁集团

**海外顶尖高校**: MIT, Stanford, Harvard, UC Berkeley, CMU, Princeton, Yale, Columbia, Cornell, Oxford, Cambridge, ETH Zurich, Toronto, Imperial College, NUS, NTU

**国内顶尖高校/机构**: 清华大学, 北京大学, 中国科学院, 上海交通大学, 浙江大学, 复旦大学, 哈尔滨工业大学, 中国人民大学, 南京大学, 武汉大学, 中山大学, 北京航空航天大学, 华中科技大学, 国防科技大学

## 依赖

- `pandas`: 数据处理
- `openai`: LLM 调用
- `jinja2`: 模板渲染（内嵌 HTML 生成）

## 输出文件

- `paper_dashboard.html`: 完整的可视化画像报告（可离线查看）
