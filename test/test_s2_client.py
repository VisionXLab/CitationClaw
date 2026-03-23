import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from citationclaw.core.s2_client import S2Client

def test_build_search_url():
    client = S2Client()
    url = client._build_search_url("Attention is All You Need")
    assert "semanticscholar.org" in url
    assert "query" in url or "search" in url

def test_parse_paper_response():
    client = S2Client()
    mock_response = {
        "paperId": "P123",
        "title": "Attention is All You Need",
        "year": 2017,
        "citationCount": 100000,
        "influentialCitationCount": 5000,
        "authors": [
            {
                "authorId": "A1",
                "name": "Ashish Vaswani",
            }
        ],
        "externalIds": {"DOI": "10.xxxx"},
        "isOpenAccess": True,
        "openAccessPdf": {"url": "https://arxiv.org/pdf/1706.03762"},
    }
    result = client._parse_paper(mock_response)
    assert result["title"] == "Attention is All You Need"
    assert result["authors"][0]["name"] == "Ashish Vaswani"
    assert result["influential_citation_count"] == 5000
    assert result["source"] == "s2"

def test_parse_author_response():
    client = S2Client()
    mock_author = {
        "authorId": "A1",
        "name": "Ashish Vaswani",
        "hIndex": 30,
        "citationCount": 200000,
        "affiliations": ["Google Brain"],
    }
    result = client._parse_author(mock_author)
    assert result["name"] == "Ashish Vaswani"
    assert result["h_index"] == 30
    assert result["citation_count"] == 200000
    assert result["affiliation"] == "Google Brain"
