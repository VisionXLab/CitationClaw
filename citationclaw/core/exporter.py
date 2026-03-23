import json
import pandas as pd
from pathlib import Path
from typing import Callable


def _is_truthy(val):
    """Parse a value that may be bool, str, or other type into a boolean."""
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() not in ('false', '0', 'nan', 'none', '')
    return bool(val)


class ResultExporter:
    def __init__(self, log_callback: Callable):
        """
        结果导出器

        Args:
            log_callback: 日志回调函数
        """
        self.log_callback = log_callback

    def highlight_renowned_scholar(self, flattened, renowned_scholar_excel_outputs):
        ## 标记学者
        def tag_scholar(df):
            """Tag scholar level based on Title/Job fields.

            Supports both Chinese and international scholar categories.
            """
            for idx, row in df.iterrows():
                title = str(row.get('Title', '') or '')
                job = str(row.get('Job', '') or '')
                combined = f"{title} {job}".lower()
                tag = ''
                # 院士级别（最高优先级）
                if any(k in combined for k in ['中国科学院院士', '中国工程院院士', '两院院士']):
                    tag = '院士'
                elif any(k in combined for k in ['院士', 'academician', 'nae', 'nas member',
                         'national academy', 'fellow of the royal society', 'frs', '欧洲科学院']):
                    tag = '其他院士'
                # 重大奖项
                elif any(k in combined for k in ['turing', '图灵', 'nobel', '诺贝尔', 'fields medal',
                         '国家最高科学技术奖', '国家科技进步', '国家自然科学奖', '国家技术发明奖',
                         'wolf prize', '沃尔夫奖', 'abel prize', '阿贝尔奖']):
                    tag = '重大奖项'
                # Fellow
                elif any(k in combined for k in [
                    'ieee fellow', 'acm fellow', 'acl fellow', 'aaai fellow',
                    'aps fellow', 'rsc fellow', 'acs fellow',
                    'ifac fellow', 'asme fellow', 'aaas fellow',
                    'iapr fellow', 'isca fellow', 'incose fellow',
                    'iet fellow', 'aaia fellow']):
                    tag = 'Fellow'
                # 国家级人才
                elif any(k in combined for k in ['杰青', '长江', '优青', '万人计划']):
                    tag = '国家级人才'
                # 知名机构核心
                elif any(k in combined for k in ['chief scientist', '首席科学家',
                         'vp of research', '研究副总裁', 'lab director', '实验室主任',
                         'distinguished scientist']):
                    tag = '知名机构核心'
                # 大学领导层
                elif any(k in combined for k in ['校长', '院长', 'president', 'dean']):
                    tag = '大学领导层'
                if tag:
                    df.at[idx, '两院院士/其他院士/Fellow'] = tag
            return df

        ## 转换df，找到大佬级别
        scholar_df = []
        for d in flattened:
            # 自引论文不纳入知名学者统计
            if _is_truthy(d.get('Is_Self_Citation', False)):
                continue
            paper_title = d.get('Paper_Title', '')
            paper_year = d.get('Paper_Year', '')
            paper_link = d.get('Paper_Link', '')
            paper_citation = d.get('Citations', 0)
            formated_renowned_scholars = d.get('Formated Renowned Scholar', [])
            if not isinstance(formated_renowned_scholars, list):
                formated_renowned_scholars = []
            for scholar in formated_renowned_scholars:
                # Support both Chinese keys (v1 legacy) and English keys (v2 new pipeline)
                name = scholar.get('name', '') or scholar.get('姓名', '')
                if name != '':
                    scholar_df.append({
                        'Name': name,
                        'Institution': scholar.get('institution', '') or scholar.get('机构', ''),
                        'Country': scholar.get('country', '') or scholar.get('国家', ''),
                        'Job': scholar.get('position', '') or scholar.get('职务', ''),
                        'Title': scholar.get('titles', '') or scholar.get('荣誉称号', ''),
                        'PaperTitle': paper_title,
                        'PaperCitations': paper_citation,
                        'PaperYear': paper_year,
                        'PaperLink': paper_link,
                        'CitingPaper': d.get('Citing_Paper', ''),
                        '两院院士/其他院士/Fellow': ''
                    })

        scholar_df = pd.DataFrame(scholar_df)
        if scholar_df.empty:
            scholar_df = pd.DataFrame(columns=['Name','Institution','Country','Job','Title',
                'PaperTitle','PaperCitations','PaperYear','PaperLink','CitingPaper','两院院士/其他院士/Fellow'])
            selected_df = scholar_df.copy()
        else:
            scholar_df = tag_scholar(scholar_df)
            # Top-tier: only 院士/其他院士/Fellow/重大奖项 (not 国家级人才/知名机构核心/大学领导层)
            _top_tiers = {'院士', '其他院士', 'Fellow', '重大奖项'}
            selected_df = scholar_df[scholar_df['两院院士/其他院士/Fellow'].isin(_top_tiers)].reset_index(drop=True)

        scholar_df.to_excel(renowned_scholar_excel_outputs[0], sheet_name='All Renowned scholars', index=False)
        selected_df.to_excel(renowned_scholar_excel_outputs[1], sheet_name='Top-tier scholars', index=False)

    # Backward-compatible alias for the old misspelled name
    highligh_renowned_scholar = highlight_renowned_scholar

    def export(
        self,
        input_file: Path,
        excel_output: Path,
        json_output: Path
    ):
        """
        导出结果为Excel和JSON格式

        Args:
            input_file: 输入JSONL文件(来自author_searcher)
            excel_output: 输出Excel文件路径
            json_output: 输出JSON文件路径
        """
        self.log_callback("正在加载数据...")

        # 读取JSONL文件
        if not input_file.exists():
            self.log_callback(f"⚠️ 输入文件不存在: {input_file}，将生成空输出文件")
            excel_output.parent.mkdir(parents=True, exist_ok=True)
            json_output.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame().to_excel(excel_output, index=False)
            with open(json_output, 'w', encoding='utf-8') as f:
                json.dump([], f, ensure_ascii=False)
            return

        data = []
        with open(input_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data.append(json.loads(line))
                except json.JSONDecodeError:
                    self.log_callback(f"⚠️ 跳过损坏的 JSON 行: {line[:80]}")

        # 展平数据结构
        flattened = []
        for line in data:
            for _, content in line.items():
                flattened.append(content)

        self.log_callback(f"共 {len(flattened)} 条记录")

        # 确保输出目录存在
        excel_output.parent.mkdir(parents=True, exist_ok=True)
        json_output.parent.mkdir(parents=True, exist_ok=True)

        # 导出Excel
        self.log_callback("正在生成Excel文件...")
        try:
            df = pd.DataFrame(flattened)
            df.to_excel(excel_output, index=False)
            self.log_callback(f"Excel文件已保存: {excel_output}")
        except Exception as e:
            self.log_callback(f"Excel导出失败: {e}")
            raise

        # ## 高亮重量级学者
        renowned_scholar_excel_output1 = excel_output.with_stem(excel_output.stem + "_all_renowned_scholar")
        renowned_scholar_excel_output1.parent.mkdir(parents=True, exist_ok=True)
        renowned_scholar_excel_output2 = excel_output.with_stem(excel_output.stem + "_top-tier_scholar")
        renowned_scholar_excel_output2.parent.mkdir(parents=True, exist_ok=True)
        renowned_scholar_excel_outputs = [renowned_scholar_excel_output1,renowned_scholar_excel_output2]
        self.log_callback("正在生成重量级学者Excel文件...")
        try:
            self.highlight_renowned_scholar(flattened,renowned_scholar_excel_outputs)
            self.log_callback(f"重量级学者Excel文件已保存: {renowned_scholar_excel_outputs}")
        except Exception as e:
            self.log_callback(f"重量级学者Excel导出失败: {e}")
            raise

        # 导出JSON
        self.log_callback("正在生成JSON文件...")
        try:
            with open(json_output, 'w', encoding='utf-8') as f:
                json.dump(flattened, f, ensure_ascii=False, indent=3)
            self.log_callback(f"JSON文件已保存: {json_output}")
        except Exception as e:
            self.log_callback(f"JSON导出失败: {e}")
            raise

        self.log_callback("导出完成!")
