from __future__ import annotations

from citationclaw.skills.base import Skill
from citationclaw.skills.phase1_citation_fetch import CitationFetchSkill
from citationclaw.skills.phase2_author_intel import AuthorIntelSkill
from citationclaw.skills.phase2_metadata import MetadataCollectionSkill
from citationclaw.skills.phase3_export import ExportSkill
from citationclaw.skills.phase3_scholar_assess import ScholarAssessSkill
from citationclaw.skills.phase4_citation_desc import CitationDescriptionSkill
from citationclaw.skills.phase4_citation_extract import CitationExtractSkill
from citationclaw.skills.phase5_report import ReportGenerateSkill


class SkillRegistry:
    """Simple registry for pipeline skills."""

    def __init__(self):
        self._skills = {}

    def register(self, skill):
        if not hasattr(skill, "name") or not hasattr(skill, "run"):
            raise TypeError(
                f"Expected a Skill with 'name' and 'run' attributes, got {type(skill).__name__}"
            )
        self._skills[skill.name] = skill

    def get(self, name: str):
        if name not in self._skills:
            raise KeyError(f"Unknown skill: {name}")
        return self._skills[name]


def build_default_registry() -> SkillRegistry:
    reg = SkillRegistry()
    # Phase 1: 施引文献检索 (unchanged)
    reg.register(CitationFetchSkill())
    # Phase 2: 作者信息采集 (old: LLM search, new: structured APIs)
    reg.register(AuthorIntelSkill())
    reg.register(MetadataCollectionSkill())
    # Phase 3: 学者影响力评估 + 导出
    reg.register(ExportSkill())
    reg.register(ScholarAssessSkill())
    # Phase 4: 引文语境提取 (old: LLM search, new: PDF parse)
    reg.register(CitationDescriptionSkill())
    reg.register(CitationExtractSkill())
    # Phase 5: 报告生成与导出
    reg.register(ReportGenerateSkill())
    return reg
