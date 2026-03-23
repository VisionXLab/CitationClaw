"""Phase 2: 作者信息采集 — Structured API metadata collection."""
import json
from pathlib import Path
from typing import List

from citationclaw.skills.base import SkillContext, SkillResult
from citationclaw.core.metadata_collector import MetadataCollector
from citationclaw.core.metadata_cache import MetadataCache


class MetadataCollectionSkill:
    name = "phase2_metadata"

    async def run(self, ctx: SkillContext, **kwargs) -> SkillResult:
        input_file = Path(kwargs["input_file"])
        output_file = Path(kwargs["output_file"])
        cache = kwargs.get("metadata_cache") or MetadataCache()

        collector = MetadataCollector(
            email=getattr(ctx.config, "openalex_email", None),
            s2_api_key=getattr(ctx.config, "s2_api_key", None),
        )

        papers = self._read_phase1(input_file)
        total = len(papers)
        results = []

        try:
            for i, paper in enumerate(papers):
                if ctx.cancel_check and ctx.cancel_check():
                    break

                title = paper.get("Citing_Paper_Title", paper.get("paper_title", ""))
                doi = paper.get("doi", "")

                # Check cache first
                cached = await cache.get(doi=doi, title=title)
                if cached:
                    ctx.log(f"[缓存命中] {title[:50]}...")
                    results.append({**paper, **cached})
                else:
                    ctx.log(f"[API查询] ({i+1}/{total}) {title[:50]}...")
                    metadata = await collector.collect(title)
                    if metadata:
                        await cache.update(doi or "", title, metadata)
                        results.append({**paper, **metadata})
                    else:
                        ctx.log(f"  ⚠ 未找到元数据: {title[:50]}")
                        results.append(paper)

                if ctx.progress:
                    ctx.progress(i + 1, total)
        finally:
            await cache.flush()
            await collector.close()

        # Write output JSONL
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        return SkillResult(name=self.name, data={
            "output_file": str(output_file),
            "total": total,
            "cached": cache.stats()["hits"],
            "queried": cache.stats()["updates"],
        })

    def _read_phase1(self, path: Path) -> List[dict]:
        papers = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    papers.append(json.loads(line))
        return papers
