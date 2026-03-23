import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from citationclaw.skills.phase3_scholar_assess import ScholarAssessSkill


def test_skill_name():
    skill = ScholarAssessSkill()
    assert skill.name == "phase3_scholar_assess"


def test_deduplicate_authors():
    skill = ScholarAssessSkill()
    papers = [
        {"authors": [{"name": "Alice"}, {"name": "Bob"}]},
        {"authors": [{"name": "alice"}, {"name": "Carol"}]},  # "alice" duplicate
    ]
    deduped = skill._deduplicate_authors(papers)
    names = [a["name"] for a in deduped]
    assert len(deduped) == 3  # Alice, Bob, Carol


def test_annotate_papers():
    skill = ScholarAssessSkill()
    papers = [
        {"title": "Paper A", "authors": [{"name": "Alice"}, {"name": "Bob"}]},
    ]
    scholar_results = {
        "Alice": {"tier": "Fellow", "honors": ["IEEE Fellow"]},
        "Bob": {"tier": "", "honors": []},
    }
    annotated = skill._annotate_papers(papers, scholar_results)
    assert len(annotated[0]["Renowned_Scholars"]) == 1
    assert annotated[0]["Renowned_Scholars"][0]["name"] == "Alice"


def test_has_run_method():
    skill = ScholarAssessSkill()
    assert hasattr(skill, "run")
    assert callable(skill.run)
