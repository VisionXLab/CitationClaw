---
name: cache_manager
description: "跨运行持久化施引论文作者信息缓存，避免重复搜索相同论文。支持增量更新和缓存统计。"
metadata: '{"citationclaw":{"emoji":"💾","requires":{"bins":[],"env":[]},"category":"support","always":true}}'
---

# 缓存管理 Skill

跨多次运行复用已搜索的作者信息，大幅提升效率并节省 API 费用。

## 核心功能

### 1. 初始化缓存

```python
from citationclaw.skills.cache_manager import AuthorInfoCache
from pathlib import Path

cache = AuthorInfoCache(
    cache_file=Path("data/cache/author_info_cache.json")
)
```

### 2. 查询缓存

```python
# 检查是否已有某论文的缓存
result = cache.get(
    paper_link="https://arxiv.org/abs/xxx",
    paper_title="论文标题"
)

# 检查特定字段是否存在
has_info = cache.has_field(
    paper_link="https://arxiv.org/abs/xxx",
    paper_title="论文标题",
    field="Searched Author Information"
)
```

### 3. 更新缓存

```python
await cache.update(
    paper_link="https://arxiv.org/abs/xxx",
    paper_title="论文标题",
    fields={
        "Searched Author-Affiliation": "作者信息...",
        "Searched Author Information": "详细作者信息...",
        "First_Author_Institution": "机构名称",
        "First_Author_Country": "国家",
        "Renowned Scholar": "知名学者列表",
        "Formated Renowned Scholar": [{...}]
    }
)
```

### 4. 获取统计

```python
stats = cache.stats()
# {
#     "total_entries": 1000,
#     "hits": 50,
#     "misses": 10,
#     "updates": 5
# }
```

## 缓存字段

可缓存的字段列表：

| 字段名 | 说明 |
|--------|------|
| `Searched Author-Affiliation` | 作者-单位列表 |
| `First_Author_Institution` | 第一作者机构 |
| `First_Author_Country` | 第一作者国家 |
| `Searched Author Information` | 详细作者信息 |
| `Author Verification` | 作者验证结果 |
| `Renowned Scholar` | 知名学者原始结果 |
| `Formated Renowned Scholar` | 格式化知名学者 |

## 缓存键策略

- **优先使用论文链接**: `paper_link` 作为缓存键
- **Fallback 到标题**: 无链接时使用小写 `paper_title`
- **永久有效**: 缓存不会过期，需手动删除文件重置

## 依赖

- 无外部依赖
- 标准库: `json`, `asyncio`, `pathlib`, `datetime`

## 文件位置

- 默认: `data/cache/author_info_cache.json`
- 自定义: 通过 `cache_file` 参数指定
