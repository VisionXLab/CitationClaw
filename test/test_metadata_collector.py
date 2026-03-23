import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from citationclaw.core.metadata_collector import MetadataCollector


def test_merge_all_sources():
    collector = MetadataCollector()
    oa = {
        "title": "Paper A", "year": 2020, "doi": "10.1234",
        "cited_by_count": 500, "openalex_id": "W1",
        "authors": [{"name": "Alice", "affiliation": "MIT", "country": "US", "openalex_id": "A1"}],
        "source": "openalex",
    }
    s2 = {
        "title": "Paper A", "year": 2020, "doi": "10.1234",
        "cited_by_count": 480, "influential_citation_count": 50, "s2_id": "P1",
        "authors": [{"name": "Alice", "s2_id": "SA1"}],
        "pdf_url": "",
        "source": "s2",
    }
    arxiv = {
        "title": "Paper A", "arxiv_id": "2001.00001", "year": 2020,
        "abstract": "We propose...",
        "authors": [{"name": "Alice", "source": "arxiv"}],
        "pdf_url": "http://arxiv.org/pdf/2001.00001",
        "source": "arxiv",
    }
    result = collector._merge(oa, s2, arxiv)
    # OpenAlex is primary for basic fields
    assert result["title"] == "Paper A"
    assert result["doi"] == "10.1234"
    assert result["authors"][0]["affiliation"] == "MIT"
    # S2 supplements h-index fields
    assert result["influential_citation_count"] == 50
    # arXiv supplements PDF url
    assert result["pdf_url"] == "http://arxiv.org/pdf/2001.00001"


def test_merge_missing_sources():
    collector = MetadataCollector()
    oa = {
        "title": "Paper B", "year": 2021, "doi": "10.5678",
        "cited_by_count": 100, "openalex_id": "W2",
        "authors": [{"name": "Bob", "affiliation": "Stanford", "country": "US", "openalex_id": "A2"}],
        "source": "openalex",
    }
    result = collector._merge(oa, None, None)
    assert result["title"] == "Paper B"
    assert result["influential_citation_count"] == 0
    assert result["pdf_url"] == ""


def test_merge_only_s2():
    collector = MetadataCollector()
    s2 = {
        "title": "Paper C", "year": 2022, "doi": "",
        "cited_by_count": 200, "influential_citation_count": 20, "s2_id": "P2",
        "authors": [{"name": "Carol", "s2_id": "SA2"}],
        "pdf_url": "https://example.com/paper.pdf",
        "source": "s2",
    }
    result = collector._merge(None, s2, None)
    assert result["title"] == "Paper C"
    assert result["authors"][0]["name"] == "Carol"
    assert result["pdf_url"] == "https://example.com/paper.pdf"


def test_merge_all_none():
    collector = MetadataCollector()
    result = collector._merge(None, None, None)
    assert result is None
