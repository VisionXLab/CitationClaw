from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Optional

from citationclaw.core.arxiv_client import ArxivClient
from citationclaw.core.s2_client import S2Client
from citationclaw.skills.base import SkillContext, SkillResult
from citationclaw.skills.phase1_s2_citation_fetch import S2CitationFetchSkill


SCAN_CAP = 3000


class S2CitationEnrichSkill:
    """Annotate a Google Scholar citation list with exact S2 edge matches."""

    name = "phase1_s2_enrich"

    async def run(self, ctx: SkillContext, **kwargs) -> SkillResult:
        title: str = kwargs["title"]
        input_file = Path(kwargs["input_file"])
        output_file = Path(kwargs["output_file"])
        scan_cap = int(kwargs.get("scan_cap") or SCAN_CAP)

        source_text = input_file.read_text(encoding="utf-8")
        lines = self._load_lines(source_text)
        gs_total = self._paper_count(lines)
        stats = {
            "gs_total": gs_total,
            "matched": 0,
            "with_context": 0,
            "doi_exact": 0,
            "arxiv_exact": 0,
            "title_exact": 0,
            "unmatched": gs_total,
            "fallback": False,
        }

        client = S2Client(api_key=getattr(ctx.config, "s2_api_key", None))
        arxiv = ArxivClient()
        helper = S2CitationFetchSkill()
        try:
            ctx.log(f"[S2 enrichment] searching target edge set: {title[:80]}")
            seed = await helper._find_seed(client, arxiv, title)
            if client.used_anonymous_fallback:
                ctx.log(
                    "[S2 enrichment] configured API key was rejected; "
                    "continuing with anonymous S2 access"
                )
            if not seed or not seed.get("paperId"):
                ctx.log("[S2 enrichment] target not found; keeping GS records unchanged")
                stats["fallback"] = True
                self._write_original(output_file, source_text)
                return SkillResult(name=self.name, data={
                    "output_file": str(output_file),
                    **stats,
                })

            light = await client.get_citations_light(seed["paperId"], scan_cap=scan_cap)
            light = [
                item for item in light
                if (item.get("citingPaper") or {}).get("paperId")
            ]
            citing_ids = [
                (item.get("citingPaper") or {}).get("paperId")
                for item in light
            ]
            details = await client.batch_papers(citing_ids)
            contexts = await client.get_citation_contexts(
                seed["paperId"], set(citing_ids)
            )

            matches = self._build_match_indexes(
                light_items=light,
                details=details,
                contexts=contexts,
                helper=helper,
            )
            stats = self._annotate_lines(
                lines=lines,
                indexes=matches,
                progress=ctx.progress,
            )
            stats["fallback"] = False
            self._write_lines(output_file, lines)
            ctx.log(
                "[S2 enrichment] "
                f"GS {stats['gs_total']} / matched {stats['matched']} "
                f"(DOI {stats['doi_exact']}, arXiv {stats['arxiv_exact']}, "
                f"title {stats['title_exact']}) / contexts {stats['with_context']} / "
                f"fallback {stats['unmatched']}"
            )
            return SkillResult(name=self.name, data={
                "output_file": str(output_file),
                **stats,
                "seed_id": seed["paperId"],
            })
        except Exception as exc:
            ctx.log(
                f"[S2 enrichment] unavailable ({str(exc)[:120]}); "
                "keeping GS records unchanged"
            )
            stats["fallback"] = True
            self._write_original(output_file, source_text)
            return SkillResult(name=self.name, data={
                "output_file": str(output_file),
                **stats,
            })
        finally:
            await client.close()
            await arxiv.close()

    @staticmethod
    def _load_lines(source_text: str) -> list[dict]:
        return [
            json.loads(line)
            for line in source_text.splitlines()
            if line.strip()
        ]

    @staticmethod
    def _paper_count(lines: list[dict]) -> int:
        return sum(
            len((page or {}).get("paper_dict") or {})
            for line in lines
            for page in line.values()
            if isinstance(page, dict)
        )

    @staticmethod
    def _normalize_title(value: str) -> str:
        text = unicodedata.normalize("NFKC", str(value or "")).casefold()
        return "".join(char for char in text if char.isalnum())

    @staticmethod
    def _extract_doi(*values) -> str:
        for value in values:
            match = re.search(
                r"10\.\d{4,9}/[^\s?#]+",
                str(value or ""),
                flags=re.IGNORECASE,
            )
            if match:
                return match.group(0).rstrip(".,);]").casefold()
        return ""

    @staticmethod
    def _extract_arxiv(*values) -> str:
        for value in values:
            text = str(value or "").strip()
            direct = re.fullmatch(
                r"(\d{4}\.\d{4,5})(?:v\d+)?",
                text,
                flags=re.IGNORECASE,
            )
            if direct:
                return direct.group(1)
            match = re.search(
                r"arxiv(?:\.org/(?:abs|pdf)/|[:/\s]+)"
                r"(\d{4}\.\d{4,5})(?:v\d+)?",
                text,
                flags=re.IGNORECASE,
            )
            if match:
                return match.group(1)
        return ""

    def _build_match_indexes(
        self,
        *,
        light_items: list,
        details: dict,
        contexts: dict,
        helper: S2CitationFetchSkill,
    ) -> dict:
        indexes = {"doi": {}, "arxiv": {}, "title": {}}
        for item in light_items:
            light = item.get("citingPaper") or {}
            paper_id = light.get("paperId")
            if not paper_id:
                continue
            paper = details.get(paper_id) or light
            metadata = helper._paper_to_metadata(paper)
            metadata["sources"] = ["s2_enrichment"]
            match = {
                "paper_id": paper_id,
                "metadata": metadata,
                "context": contexts.get(paper_id) or {},
            }
            doi = self._extract_doi(metadata.get("doi"))
            arxiv_id = self._extract_arxiv(metadata.get("arxiv_id"))
            normalized_title = self._normalize_title(
                metadata.get("title") or light.get("title")
            )
            if doi:
                indexes["doi"].setdefault(doi, match)
            if arxiv_id:
                indexes["arxiv"].setdefault(arxiv_id, match)
            if normalized_title:
                indexes["title"].setdefault(normalized_title, match)
        return indexes

    def _match_paper(self, paper: dict, indexes: dict) -> tuple[Optional[dict], str]:
        doi = self._extract_doi(
            paper.get("doi"),
            paper.get("paper_link"),
            paper.get("gs_pdf_link"),
        )
        if doi and doi in indexes["doi"]:
            return indexes["doi"][doi], "doi_exact"

        arxiv_id = self._extract_arxiv(
            paper.get("arxiv_id"),
            paper.get("paper_link"),
            paper.get("gs_pdf_link"),
        )
        if arxiv_id and arxiv_id in indexes["arxiv"]:
            return indexes["arxiv"][arxiv_id], "arxiv_exact"

        title = self._normalize_title(paper.get("paper_title"))
        if title and title in indexes["title"]:
            return indexes["title"][title], "title_exact"
        return None, "unmatched"

    def _annotate_lines(self, *, lines: list[dict], indexes: dict, progress=None) -> dict:
        total = self._paper_count(lines)
        stats = {
            "gs_total": total,
            "matched": 0,
            "with_context": 0,
            "doi_exact": 0,
            "arxiv_exact": 0,
            "title_exact": 0,
            "unmatched": 0,
        }
        done = 0
        for line in lines:
            for page in line.values():
                if not isinstance(page, dict):
                    continue
                for paper in (page.get("paper_dict") or {}).values():
                    match, status = self._match_paper(paper, indexes)
                    paper["s2_match_status"] = status
                    paper["s2_match_score"] = 1.0 if match else 0.0
                    if not match:
                        stats["unmatched"] += 1
                    else:
                        context = match["context"]
                        metadata = match["metadata"]
                        paper["source"] = "scholar+s2"
                        paper["s2_id"] = match["paper_id"]
                        paper["doi"] = metadata.get("doi", "")
                        paper["arxiv_id"] = metadata.get("arxiv_id", "")
                        paper["venue"] = metadata.get("venue", "")
                        paper["pdf_url"] = metadata.get("pdf_url", "")
                        paper["s2_contexts"] = context.get("contexts") or []
                        paper["s2_intents"] = context.get("intents") or []
                        paper["s2_contextsWithIntent"] = (
                            context.get("contextsWithIntent") or []
                        )
                        paper["s2_isInfluential"] = (
                            context.get("isInfluential") or False
                        )
                        paper["s2_metadata"] = metadata
                        stats["matched"] += 1
                        stats[status] += 1
                        if paper["s2_contexts"]:
                            stats["with_context"] += 1
                    done += 1
                    if progress:
                        progress(done, total)
        return stats

    @staticmethod
    def _write_lines(output_file: Path, lines: list[dict]):
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with output_file.open("w", encoding="utf-8") as handle:
            for line in lines:
                handle.write(json.dumps(line, ensure_ascii=False) + "\n")

    @staticmethod
    def _write_original(output_file: Path, source_text: str):
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(source_text, encoding="utf-8")
