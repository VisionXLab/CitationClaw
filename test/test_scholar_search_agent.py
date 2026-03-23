import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from citationclaw.core.scholar_search_agent import ScholarSearchAgent, ScholarResult, SCHOLAR_SEARCH_PROMPT


def test_prompt_has_placeholders():
    assert "{paper_title}" in SCHOLAR_SEARCH_PROMPT
    assert "{author_data}" in SCHOLAR_SEARCH_PROMPT


def test_parse_response_with_scholars():
    agent = ScholarSearchAgent()
    text = """
$$$分隔符$$$
Geoffrey Hinton
University of Toronto
Canada
Professor Emeritus
Turing Award, ACM Fellow, FRS
$$$分隔符$$$
Yann LeCun
Meta AI / New York University
USA
VP & Chief AI Scientist
Turing Award, ACM Fellow, IEEE Fellow
$$$分隔符$$$
"""
    results = agent._parse_response(text)
    assert len(results) == 2
    assert results[0].name == "Geoffrey Hinton"
    assert results[0].tier == "Academician"  # FRS matches Academician before Turing
    assert results[1].name == "Yann LeCun"
    assert results[1].tier == "Fellow"  # ACM/IEEE Fellow matches before Turing


def test_parse_response_no_scholars():
    agent = ScholarSearchAgent()
    assert agent._parse_response("无") == []
    assert agent._parse_response("无任何顶级学者") == []


def test_determine_tier():
    agent = ScholarSearchAgent()
    r = ScholarResult(name="Test", honors="IEEE Fellow")
    assert agent._determine_tier(r) == "Fellow"
    r2 = ScholarResult(name="Test", honors="中国科学院院士")
    assert agent._determine_tier(r2) == "Academician"
    r3 = ScholarResult(name="Test", position="Chief Scientist at Google")
    assert agent._determine_tier(r3) == "Industry Leader"


def test_agent_without_config():
    """Agent without API key should return empty results gracefully."""
    agent = ScholarSearchAgent()  # no api_key
    import asyncio
    results = asyncio.get_event_loop().run_until_complete(
        agent.search_paper_authors("Test Paper", [{"name": "Alice"}])
    )
    assert results == []
