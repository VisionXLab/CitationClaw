import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import json
import pytest
from pathlib import Path
from citationclaw.core.scholar_search_agent import ScholarSearchAgent, ScholarResult


@pytest.fixture
def known_scholars():
    path = Path(__file__).parent / "fixtures" / "known_scholars.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_known_scholars_fixture_loaded(known_scholars):
    assert len(known_scholars) >= 5
    assert known_scholars[0]["name"] == "Andrew Ng"


def test_parse_response_format():
    """Test that _parse_response correctly parses scholar output format."""
    agent = ScholarSearchAgent()
    text = """$$$分隔符$$$
Geoffrey Hinton
University of Toronto
Canada
Professor Emeritus
Turing Award winner, ACM Fellow
$$$分隔符$$$"""
    results = agent._parse_response(text)
    assert len(results) >= 1
    assert results[0].name == "Geoffrey Hinton"
    assert "Turing" in results[0].honors


def test_tier_determination():
    agent = ScholarSearchAgent()
    # Test with ScholarResult objects (correct API)
    assert agent._determine_tier(
        ScholarResult(honors="Turing Award winner", position="Professor")
    ) == "Major Award Winner"
    assert agent._determine_tier(
        ScholarResult(honors="中国科学院院士", position="教授")
    ) == "Academician"
    assert agent._determine_tier(
        ScholarResult(honors="IEEE Fellow", position="Professor")
    ) == "Fellow"
    assert agent._determine_tier(
        ScholarResult(honors="杰青", position="教授")
    ) == "National Talent (China)"
    assert agent._determine_tier(
        ScholarResult(honors="", position="")
    ) == ""


def test_normalize_country():
    assert ScholarSearchAgent._normalize_country("US") == "美国"
    assert ScholarSearchAgent._normalize_country("China") == "中国"
    assert ScholarSearchAgent._normalize_country("中国") == "中国"
    assert ScholarSearchAgent._normalize_country("UK") == "英国"
    assert ScholarSearchAgent._normalize_country(None) == ""


def test_extract_name_keys():
    keys = ScholarSearchAgent._extract_name_keys("李德仁 (Deren Li)")
    assert "李德仁" in keys
    assert "deren li" in keys

    keys2 = ScholarSearchAgent._extract_name_keys("Z Y Zou (Zhengxia Zou / 邹征夏)")
    assert "邹征夏" in keys2
    assert "zhengxia zou" in keys2
