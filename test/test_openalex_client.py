import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from citationclaw.core.openalex_client import OpenAlexClient

def test_build_search_url():
    client = OpenAlexClient()
    url = client._build_search_url("Attention is All You Need")
    assert "openalex.org" in url
    assert "search" in url or "filter" in url

def test_parse_work_response():
    client = OpenAlexClient()
    mock_response = {
        "id": "W123",
        "title": "Attention is All You Need",
        "publication_year": 2017,
        "cited_by_count": 100000,
        "authorships": [
            {
                "author": {"id": "A1", "display_name": "Ashish Vaswani"},
                "institutions": [{"display_name": "Google Brain", "country_code": "US"}],
            }
        ],
        "doi": "https://doi.org/10.xxxx",
    }
    result = client._parse_work(mock_response)
    assert result["title"] == "Attention is All You Need"
    assert result["authors"][0]["name"] == "Ashish Vaswani"
    assert result["authors"][0]["affiliation"] == "Google Brain"
    assert result["authors"][0]["country"] == "US"
    assert result["source"] == "openalex"

def test_parse_author_response():
    client = OpenAlexClient()
    mock_author = {
        "id": "A1",
        "display_name": "Ashish Vaswani",
        "cited_by_count": 200000,
        "summary_stats": {"h_index": 30},
        "affiliations": [{"institution": {"display_name": "Google Brain"}}],
    }
    result = client._parse_author(mock_author)
    assert result["name"] == "Ashish Vaswani"
    assert result["h_index"] == 30
    assert result["citation_count"] == 200000
