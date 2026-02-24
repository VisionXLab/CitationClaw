"""
Phase 4: 批量搜索每篇引用论文对目标论文的引用描述
"""
import asyncio
import pandas as pd
from pathlib import Path
from typing import Callable, Optional
from openai import AsyncOpenAI
import httpx


class CitingDescriptionSearcher:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        log_callback: Callable,
        progress_callback: Callable,
    ):
        http_client = httpx.AsyncClient(
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=10),
            timeout=60.0
        )
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            http_client=http_client,
            max_retries=2,
        )
        self.model = model
        self.log = log_callback
        self.progress = progress_callback

    async def _search_fn(self, query: str, retries: int = 3) -> str:
        """调用搜索API（启用web_search_options）"""
        for i in range(retries):
            try:
                comp = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": query}],
                    extra_body={"web_search_options": {}}
                )
                return comp.choices[0].message.content or ""
            except Exception as e:
                if i < retries - 1:
                    await asyncio.sleep(2 ** i)
                else:
                    self.log(f"⚠️ 搜索API错误: {e}")
                    return "NONE"

    async def _find_description(
        self, target_title: str, citing_title: str, citing_url: str
    ) -> str:
        """搜索 citing_title 中对 target_title 的引用描述"""
        # Step1: 找目标论文作者
        q1 = (f"请搜索论文《{target_title}》的所有作者，"
              f"只需按顺序列出姓名，格式：作者1, 作者2, ...")
        authors = await self._search_fn(q1)

        # Step2: 搜索引用描述
        q2 = (
            f"请访问以下链接，阅读论文《{citing_title}》全文：{citing_url}\n\n"
            f"找出该论文在正文中引用《{target_title}》({authors})的具体描述或表述。\n"
            f"要求：\n"
            f"1. 只摘录原文中真实存在的引用描述，不能编造。\n"
            f"2. 直接引用原文句子/段落，注明出现在哪个部分（Introduction/Related Work等）。\n"
            f"3. 若是正面描述需强调。\n"
            f"4. 找不到则输出'无法找到相关引用描述'。"
        )
        return await self._search_fn(q2)

    async def search(
        self,
        input_excel: Path,
        output_excel: Path,
        parallel_workers: int = 5,
        cancel_check: Optional[Callable] = None,
    ) -> Path:
        """
        读取 input_excel（result.xlsx），为每行搜索引用描述，
        写入 Citing_Description 列，保存到 output_excel。
        """
        df = pd.read_excel(input_excel)
        total = len(df)
        self.log(f"共 {total} 篇论文需要搜索引用描述")

        df['Citing_Description'] = ''
        semaphore = asyncio.Semaphore(parallel_workers)
        completed = 0

        async def process_row(idx, row, sem):
            nonlocal completed
            async with sem:
                if cancel_check and cancel_check():
                    return idx, ""
                target = str(row.get('Citing_Paper', '') or '')
                citing_title = str(row.get('Paper_Title', '') or '')
                citing_url = str(row.get('Paper_Link', '') or '')
                if not target or not citing_title:
                    completed += 1
                    self.progress(completed, total)
                    return idx, ""
                desc = await self._find_description(target, citing_title, citing_url)
                completed += 1
                self.progress(completed, total)
                self.log(f"[{completed}/{total}] 引用描述搜索完成: {citing_title[:40]}...")
                return idx, desc

        tasks = [
            asyncio.create_task(process_row(i, row, semaphore))
            for i, row in df.iterrows()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for item in results:
            if not isinstance(item, Exception):
                i, desc = item
                df.at[i, 'Citing_Description'] = desc

        output_excel.parent.mkdir(parents=True, exist_ok=True)
        df.to_excel(output_excel, index=False)
        self.log(f"引用描述已保存: {output_excel}")
        return output_excel
