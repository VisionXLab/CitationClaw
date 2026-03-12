---
name: result_exporter
description: "将分析结果导出为 Excel 和 JSON 格式，生成知名学者专项报告。支持数据展平和格式化。"
metadata: '{"citationclaw":{"emoji":"📁","requires":{"bins":[],"env":[]},"category":"support","always":true}}'
---

# 结果导出 Skill

将作者搜索结果导出为 Excel 和 JSON 格式，便于后续分析和分享。

## 核心功能

### 1. 导出结果

```python
from citationclaw.skills.result_exporter import ResultExporter
from pathlib import Path

exporter = ResultExporter(log_callback=print)

exporter.export(
    input_file=Path("data/author_results.jsonl"),
    excel_output=Path("data/paper_results.xlsx"),
    json_output=Path("data/paper_results.json")
)
```

### 2. 导出知名学者专项报告

```python
exporter.highligh_renowned_scholar(
    flattened=data_list,
    renowned_scholar_excel_outputs=[
        Path("data/paper_all_renowned_scholar.xlsx"),
        Path("data/paper_top-tier_scholar.xlsx")
    ]
)
```

## 输出文件

### 主报告
- `paper_results.xlsx`: 包含所有施引论文的完整信息
- `paper_results.json`: JSON 格式的完整数据

### 知名学者专项
- `paper_all_renowned_scholar.xlsx`: 所有知名学者列表
- `paper_top-tier_scholar.xlsx`: 顶尖学者（院士级别）

## 数据字段

Excel 包含的主要字段：

- `Paper_Title`: 被引论文标题
- `Paper_Year`: 被引论文年份
- `Citations`: 被引次数
- `Paper_Link`: Google Scholar 链接
- `Citing_Paper`: 施引论文标题
- `Citing_Authors`: 施引论文作者（Google Scholar 显示）
- `Citing_Year`: 施引论文年份
- `Searched Author-Affiliation`: 搜索到的作者-单位
- `Searched Author Information`: 详细作者信息
- `First_Author_Institution`: 第一作者机构
- `First_Author_Country`: 第一作者国家
- `Renowned Scholar`: 知名学者原始信息
- `Formated Renowned Scholar`: 格式化知名学者
- `Is_Self_Citation`: 是否自引

## 学者分类标记

自动标记以下学者类型：

| 标记 | 条件 |
|------|------|
| 院士 | 中国科学院院士 或 中国工程院院士 |
| 其他院士 | 包含"院士"但不属于两院 |
| Fellow | IEEE/ACM/ACL 等 Fellow |

## 依赖

- `pandas`: Excel 生成
- `json`: JSON 导出

## 数据格式

输入为 JSONL 格式（每行一个 JSON 对象），自动展平嵌套结构。
