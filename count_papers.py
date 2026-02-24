"""
统计JSONL文件中的论文数量
"""
import json
import sys
from pathlib import Path

# 获取文件路径（从命令行参数或默认值）
if len(sys.argv) > 1:
    file_path = Path(sys.argv[1])
else:
    file_path = Path('data/jsonl/paper-20260208_201151_citing_papers.jsonl')

if not file_path.exists():
    print(f"[ERROR] 文件不存在: {file_path}")
    sys.exit(1)

print("=" * 80)
print(f"文件: {file_path.name}")
print("=" * 80)

total_papers = 0
pages_info = []

with open(file_path, 'r', encoding='utf-8') as f:
    for line_num, line in enumerate(f, 1):
        try:
            data = json.loads(line)

            # 每行是一个字典，key是page_id，value是page内容
            for page_id, page_content in data.items():
                paper_dict = page_content.get('paper_dict', {})
                paper_count = len(paper_dict)
                total_papers += paper_count

                pages_info.append({
                    'page_id': page_id,
                    'paper_count': paper_count,
                    'has_next': page_content.get('next_page') != 'EMPTY'
                })

                print(f"{page_id}: {paper_count} 篇论文")

        except json.JSONDecodeError as e:
            print(f"[ERROR] 第 {line_num} 行JSON解析失败: {e}")
        except Exception as e:
            print(f"[ERROR] 第 {line_num} 行处理失败: {e}")

print()
print("=" * 80)
print("统计汇总")
print("=" * 80)
print(f"总行数（JSONL行）: {len(pages_info)}")
print(f"总页数: {len(pages_info)}")
print(f"总论文数: {total_papers}")

if pages_info:
    last_page = pages_info[-1]
    print(f"最后一页: {last_page['page_id']}")
    print(f"最后一页论文数: {last_page['paper_count']}")
    print(f"是否有下一页: {'是' if last_page['has_next'] else '否'}")

    # 检查是否有重复页面
    page_ids = [p['page_id'] for p in pages_info]
    unique_ids = set(page_ids)
    if len(page_ids) != len(unique_ids):
        print()
        print("[WARNING] 检测到重复的页面！")
        from collections import Counter
        duplicates = {pid: count for pid, count in Counter(page_ids).items() if count > 1}
        for pid, count in duplicates.items():
            print(f"  - {pid} 重复了 {count} 次")
    else:
        print()
        print("[OK] 没有检测到重复数据")

print("=" * 80)
