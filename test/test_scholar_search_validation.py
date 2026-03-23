import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import json
import pytest
from pathlib import Path
from citationclaw.core.scholar_search_agent import ScholarSearchAgent


@pytest.fixture
def known_scholars():
    path = Path(__file__).parent / "fixtures" / "known_scholars.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_known_scholars_fixture_loaded(known_scholars):
    assert len(known_scholars) >= 5
    assert known_scholars[0]["name"] == "Andrew Ng"


def test_search_steps_for_known_scholars(known_scholars):
    agent = ScholarSearchAgent()
    for scholar in known_scholars:
        steps = agent._build_search_steps(scholar["name"], scholar["affiliation"])
        assert len(steps) >= 2
        assert scholar["name"] in steps[0].query


def test_honor_extraction_accuracy():
    """Test that honor keyword extraction works for known patterns."""
    agent = ScholarSearchAgent()

    # Simulate web text mentioning known honors
    text_en = "Geoffrey Hinton is a Turing Award winner and Fellow of the Royal Society (FRS). He is also an ACM Fellow."
    honors = agent._extract_honors_keywords(text_en)
    assert "Turing Award" in honors
    assert "ACM Fellow" in honors

    text_cn = "张钹教授是中国科学院院士，在人工智能领域做出了杰出贡献。"
    honors_cn = agent._extract_honors_keywords(text_cn)
    assert "中国科学院院士" in honors_cn


def test_tier_determination():
    agent = ScholarSearchAgent()
    assert agent._determine_tier({"Turing Award"}) == "Major Award Winner"
    assert agent._determine_tier({"中国科学院院士"}) == "Academician"
    assert agent._determine_tier({"IEEE Fellow"}) == "Fellow"
    assert agent._determine_tier({"杰青"}) == "National Talent (China)"
    assert agent._determine_tier(set()) == ""
