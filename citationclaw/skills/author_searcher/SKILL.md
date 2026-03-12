---
name: author_searcher
description: "使用 LLM 搜索施引论文作者的学术信息，识别知名学者、院士、Fellow、企业大佬等。支持作者验证和自引检测。"
metadata: '{"citationclaw":{"emoji":"👥","requires":{"bins":[],"env":["OPENAI_API_KEY"]},"category":"core","always":true}}'
---

# 作者信息搜索 Skill

使用 LLM API 搜索施引论文作者的学术背景信息，识别高影响力学者。

## 核心功能

### 1. 搜索作者信息

```python
from citationclaw.skills.author_searcher import AuthorSearcher
from citationclaw.skills.cache_manager import AuthorInfoCache

searcher = AuthorSearcher(
    api_key="your-api-key",
    base_url="https://api.gpt.ge/v1/",
    model="gemini-3-flash-preview-search",
    log_callback=print,
    progress_callback=lambda c, t: print(f"{c}/{t}"),
    author_cache=AuthorInfoCache()
)

results = await searcher.search_from_citing_papers(
    input_file="data/citing_papers.jsonl",
    output_file="data/author_results.jsonl",
    config=config_dict,
    target_paper_authors="Author1 (Inst1), Author2 (Inst2)"
)
```

### 2. 识别的学者类型

- **两院院士**: 中国科学院院士、中国工程院院士
- **学术 Fellow**: IEEE/ACM/ACL/AAAI 等学会 Fellow
- **国际奖项**: 诺贝尔奖、图灵奖得主
- **人才计划**: 国家杰青、长江学者、优青
- **企业大佬**: Google/DeepMind/Meta/OpenAI 等首席科学家、VP

### 3. 支持的配置选项

| 参数 | 类型 | 说明 |
|------|------|------|
| `api_key` | str | LLM API Key |
| `base_url` | str | API Base URL |
| `model` | str | 搜索模型（需支持 web search） |
| `prompt1` | str | 作者列表搜索 Prompt |
| `prompt2` | str | 作者详情搜索 Prompt |
| `enable_renowned_scholar` | bool | 启用知名学者二次筛选 |
| `renowned_scholar_model` | str | 二次筛选模型 |
| `enable_author_verification` | bool | 启用作者信息校验 |
| `author_verify_model` | str | 校验模型 |
| `parallel_author_search` | int | 并行搜索数量 |
| `sleep_between_authors` | float | 请求间隔（秒） |

### 4. 输出字段

- `Searched Author-Affiliation`: 搜索到的作者-单位列表
- `Searched Author Information`: 详细作者信息
- `First_Author_Institution`: 第一作者机构
- `First_Author_Country`: 第一作者国家
- `Author Verification`: 作者信息验证结果
- `Renowned Scholar`: 知名学者原始结果
- `Formated Renowned Scholar`: 格式化后的知名学者信息
- `Is_Self_Citation`: 是否自引

## 依赖

- `openai`: OpenAI 兼容客户端
- `httpx`: 异步 HTTP
- `cache_manager` skill: 作者信息缓存

## 缓存机制

自动使用 `cache_manager` skill 缓存搜索结果，避免重复查询相同论文。
