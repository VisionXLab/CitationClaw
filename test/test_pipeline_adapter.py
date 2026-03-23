import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import json
import pytest
from citationclaw.core.pipeline_adapter import PipelineAdapter


def test_flatten_phase1():
    adapter = PipelineAdapter()
    phase1_line = {
        "page_0": {
            "paper_dict": {
                "paper_0": {
                    "paper_link": "https://scholar.google.com/xyz",
                    "paper_title": "Test Paper A",
                    "paper_year": 2023,
                    "citation": "42",
                    "authors": {
                        "author_0_Alice Smith": "https://scholar.google.com/alice",
                        "author_1_Bob Jones": ""
                    }
                }
            }
        }
    }
    papers = adapter.flatten_phase1_line(phase1_line)
    assert len(papers) == 1
    p = papers[0]
    assert p["paper_title"] == "Test Paper A"
    assert p["paper_link"] == "https://scholar.google.com/xyz"
    assert p["paper_year"] == 2023
    assert "Alice Smith" in str(p["authors_raw"])


def test_flatten_phase1_file(tmp_path):
    adapter = PipelineAdapter()
    f = tmp_path / "test.jsonl"
    line1 = {"page_0": {"paper_dict": {"paper_0": {"paper_title": "A", "paper_link": "", "paper_year": 2020, "citation": "1", "authors": {}}}}}
    line2 = {"page_1": {"paper_dict": {"paper_0": {"paper_title": "B", "paper_link": "", "paper_year": 2021, "citation": "2", "authors": {}}}}}
    f.write_text(json.dumps(line1) + "\n" + json.dumps(line2) + "\n")
    papers = adapter.flatten_phase1_file(f)
    assert len(papers) == 2
    assert papers[0]["paper_title"] == "A"
    assert papers[1]["paper_title"] == "B"


def test_to_legacy_record():
    adapter = PipelineAdapter()
    paper = {
        "paper_title": "Test Paper", "paper_link": "https://scholar.google.com/xyz",
        "paper_year": 2023, "citation": "42", "page_id": "page_0", "paper_id": "paper_0",
        "authors_raw": {"author_0_Alice Smith": "url1"},
    }
    metadata = {
        "title": "Test Paper",
        "authors": [
            {"name": "Alice Smith", "affiliation": "MIT", "country": "US", "openalex_id": "A1"},
            {"name": "Bob Jones", "affiliation": "Stanford", "country": "US", "openalex_id": "A2"},
        ],
        "sources": ["openalex", "s2"],
        "doi": "10.1234/test",
        "cited_by_count": 100,
        "influential_citation_count": 5,
        "pdf_url": "https://arxiv.org/pdf/2301.00001",
    }
    self_cite = {"is_self_citation": False, "method": "none"}
    scholars = [{"name": "Bob Jones", "tier": "Fellow", "honors": ["IEEE Fellow"], "affiliation": "Stanford"}]
    record = adapter.to_legacy_record(paper=paper, metadata=metadata, self_citation=self_cite,
        renowned_scholars=scholars, citing_paper="Target Paper", record_index=1)
    assert "1" in record
    inner = record["1"]
    assert inner["Paper_Title"] == "Test Paper"
    assert inner["Paper_Link"] == "https://scholar.google.com/xyz"
    assert inner["Citing_Paper"] == "Target Paper"
    assert inner["Is_Self_Citation"] == False
    assert "MIT" in inner["First_Author_Institution"]
    assert inner["First_Author_Country"] in ("US", "美国")
    assert "Alice Smith" in inner["Searched Author-Affiliation"]
    assert "Bob Jones" in inner["Searched Author-Affiliation"]
    assert inner["Data_Sources"] == "openalex,s2"
    assert "IEEE Fellow" in str(inner["Renowned Scholar"])
    assert isinstance(inner["Formated Renowned Scholar"], list)
    assert inner["Formated Renowned Scholar"][0]["name"] == "Bob Jones"


def test_to_legacy_no_metadata():
    adapter = PipelineAdapter()
    paper = {"paper_title": "Unknown Paper", "paper_link": "", "paper_year": None,
             "citation": "0", "authors_raw": {}, "page_id": "", "paper_id": ""}
    record = adapter.to_legacy_record(paper=paper, metadata=None,
        self_citation={"is_self_citation": False, "method": "none"},
        renowned_scholars=[], citing_paper="Target", record_index=1)
    inner = record["1"]
    assert inner["Paper_Title"] == "Unknown Paper"
    assert inner["Data_Sources"] == ""
    assert inner["Searched Author-Affiliation"] == ""
