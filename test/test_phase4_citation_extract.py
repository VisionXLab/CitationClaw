import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from citationclaw.skills.phase4_citation_extract import CitationExtractSkill


def test_skill_name():
    skill = CitationExtractSkill()
    assert skill.name == "phase4_citation_extract"


def test_read_jsonl(tmp_path):
    import json
    skill = CitationExtractSkill()
    jsonl_file = tmp_path / "test.jsonl"
    jsonl_file.write_text(
        json.dumps({"title": "Paper A"}) + "\n" +
        json.dumps({"title": "Paper B"}) + "\n"
    )
    papers = skill._read_jsonl(jsonl_file)
    assert len(papers) == 2
    assert papers[0]["title"] == "Paper A"


def test_has_run_method():
    skill = CitationExtractSkill()
    assert hasattr(skill, "run")
    assert callable(skill.run)
