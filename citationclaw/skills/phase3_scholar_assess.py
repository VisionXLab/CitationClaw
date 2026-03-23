"""Phase 3: 学者影响力评估 — Pre-filter + browser search + LLM assess."""
import json
from pathlib import Path
from typing import List, Dict, Set

from citationclaw.skills.base import SkillContext, SkillResult
from citationclaw.core.scholar_prefilter import ScholarPreFilter
from citationclaw.core.scholar_search_agent import ScholarSearchAgent


class ScholarAssessSkill:
    name = "phase3_scholar_assess"

    async def run(self, ctx: SkillContext, **kwargs) -> SkillResult:
        input_file = Path(kwargs["input_file"])
        output_file = Path(kwargs["output_file"])
        scholar_cache = kwargs.get("scholar_cache", {})

        prefilter = ScholarPreFilter()
        search_agent = ScholarSearchAgent(
            browser_manager=kwargs.get("browser_manager"),
            llm_client=kwargs.get("llm_client"),
        )

        papers = self._read_jsonl(input_file)

        # Step 1: Deduplicate authors across all papers
        all_authors = self._deduplicate_authors(papers)
        ctx.log(f"[学者评估] 共 {len(all_authors)} 位去重作者")

        # Step 2: Pre-filter
        candidates, non_candidates = prefilter.filter_candidates(all_authors)
        ctx.log(f"[预过滤] {len(candidates)} 位候选, {len(non_candidates)} 位普通学者")

        # Step 3: Search candidates (browser + LLM)
        scholar_results = {}
        for i, author in enumerate(candidates):
            name = author.get("name", "")
            if ctx.cancel_check and ctx.cancel_check():
                break

            # Check cache
            cache_key = f"{name}||{author.get('affiliation', '')}".lower()
            if cache_key in scholar_cache:
                scholar_results[name] = scholar_cache[cache_key]
                ctx.log(f"  [缓存] {name}")
                continue

            ctx.log(f"  [搜索] ({i+1}/{len(candidates)}) {name}...")
            try:
                result = await search_agent.search(
                    name=name,
                    affiliation=author.get("affiliation", ""),
                    h_index=author.get("h_index", 0),
                    citation_count=author.get("citation_count", 0),
                )
                scholar_results[name] = result
                scholar_cache[cache_key] = result
            except Exception as e:
                ctx.log(f"  ⚠ 搜索失败: {name} - {e}")

            if ctx.progress:
                ctx.progress(i + 1, len(candidates))

        # Step 4: Mark non-candidates as regular scholars
        for author in non_candidates:
            name = author.get("name", "")
            if name not in scholar_results:
                scholar_results[name] = {
                    "name": name,
                    "affiliation": author.get("affiliation", ""),
                    "tier": "",
                    "honors": [],
                    "source": "prefilter_skip",
                }

        # Step 5: Annotate papers with scholar tier info
        enriched = self._annotate_papers(papers, scholar_results)

        # Write output
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            for r in enriched:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        return SkillResult(name=self.name, data={
            "output_file": str(output_file),
            "total_authors": len(all_authors),
            "candidates_searched": len(candidates),
            "scholars_found": sum(1 for r in scholar_results.values() if r.get("tier")),
        })

    def _read_jsonl(self, path: Path) -> list:
        papers = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    papers.append(json.loads(line))
        return papers

    def _deduplicate_authors(self, papers: List[dict]) -> List[dict]:
        """Deduplicate authors across all papers by name."""
        seen: Dict[str, dict] = {}
        for paper in papers:
            for author in paper.get("authors", []):
                name = author.get("name", "").strip()
                if name and name.lower() not in seen:
                    seen[name.lower()] = author
        return list(seen.values())

    def _annotate_papers(self, papers: List[dict], scholar_results: dict) -> List[dict]:
        """Add scholar tier info to each paper's author data."""
        for paper in papers:
            renowned = []
            for author in paper.get("authors", []):
                name = author.get("name", "")
                result = scholar_results.get(name, {})
                if result.get("tier"):
                    renowned.append({
                        "name": name,
                        "tier": result["tier"],
                        "honors": result.get("honors", []),
                    })
            paper["Renowned_Scholars"] = renowned
        return papers
