import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from citationclaw.core.scholar_prefilter import ScholarPreFilter


def test_high_h_index_is_candidate():
    pf = ScholarPreFilter()
    author = {"name": "Alice", "h_index": 50, "citation_count": 5000, "affiliation": "Unknown University"}
    assert pf.is_candidate(author) is True


def test_high_citations_is_candidate():
    pf = ScholarPreFilter()
    author = {"name": "Bob", "h_index": 10, "citation_count": 15000, "affiliation": "Small Lab"}
    assert pf.is_candidate(author) is True


def test_known_institution_is_candidate():
    pf = ScholarPreFilter()
    author = {"name": "Carol", "h_index": 5, "citation_count": 100, "affiliation": "Google"}
    assert pf.is_candidate(author) is True


def test_unknown_low_metrics_not_candidate():
    pf = ScholarPreFilter()
    author = {"name": "Dave", "h_index": 5, "citation_count": 100, "affiliation": "Small University"}
    assert pf.is_candidate(author) is False


def test_chinese_university_is_candidate():
    pf = ScholarPreFilter()
    author = {"name": "张三", "h_index": 5, "citation_count": 100, "affiliation": "清华大学"}
    assert pf.is_candidate(author) is True


def test_filter_candidates_split():
    pf = ScholarPreFilter()
    authors = [
        {"name": "A", "h_index": 50, "citation_count": 0, "affiliation": ""},
        {"name": "B", "h_index": 3, "citation_count": 50, "affiliation": "Unknown"},
        {"name": "C", "h_index": 5, "citation_count": 100, "affiliation": "Stanford University"},
    ]
    candidates, non_candidates = pf.filter_candidates(authors)
    assert len(candidates) == 2  # A (h_index) and C (Stanford)
    assert len(non_candidates) == 1  # B
