import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest


def test_phase4_skill_exists():
    """Verify the new Phase 4 skill can be imported."""
    from citationclaw.skills.phase4_citation_extract import CitationExtractSkill
    skill = CitationExtractSkill()
    assert skill.name == "phase4_citation_extract"


def test_prompt_template_exists():
    """Verify citation_extract prompt template is available."""
    from citationclaw.config.prompt_loader import PromptLoader
    loader = PromptLoader()
    text = loader.get("citation_extract")
    assert "{citing_title}" in text
    assert "{target_title}" in text
    assert "{parsed_paragraphs}" in text
