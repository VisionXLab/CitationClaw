import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from citationclaw.core.arxiv_client import ArxivClient

def test_build_search_url():
    client = ArxivClient()
    url = client._build_search_url("Attention is All You Need")
    assert "arxiv.org" in url

def test_parse_entry():
    """Test parsing an arXiv Atom feed entry (as dict)."""
    client = ArxivClient()
    mock_entry = {
        "id": "http://arxiv.org/abs/1706.03762v5",
        "title": "Attention Is All You Need",
        "summary": "The dominant sequence transduction models...",
        "authors": [
            {"name": "Ashish Vaswani"},
            {"name": "Noam Shazeer"},
        ],
        "published": "2017-06-12T17:57:34Z",
        "links": [
            {"href": "http://arxiv.org/abs/1706.03762v5", "type": "text/html"},
            {"href": "http://arxiv.org/pdf/1706.03762v5", "type": "application/pdf"},
        ],
    }
    result = client._parse_entry(mock_entry)
    assert result["title"] == "Attention Is All You Need"
    assert result["authors"][0]["name"] == "Ashish Vaswani"
    assert "1706.03762" in result["arxiv_id"]
    assert result["pdf_url"] == "http://arxiv.org/pdf/1706.03762v5"
    assert result["source"] == "arxiv"

def test_extract_arxiv_id():
    client = ArxivClient()
    assert client._extract_arxiv_id("http://arxiv.org/abs/1706.03762v5") == "1706.03762"
    assert client._extract_arxiv_id("http://arxiv.org/abs/2301.00001v1") == "2301.00001"
