# test/test_new_pipeline_e2e.py
"""Smoke test: verify the new pipeline components are properly wired."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import json
from citationclaw.core.pipeline_adapter import PipelineAdapter
from citationclaw.core.metadata_collector import MetadataCollector
from citationclaw.core.self_citation import SelfCitationDetector
from citationclaw.core.scholar_prefilter import ScholarPreFilter
from citationclaw.skills.phase2_metadata import MetadataCollectionSkill
from citationclaw.skills.phase3_scholar_assess import ScholarAssessSkill
from citationclaw.skills.phase4_citation_extract import CitationExtractSkill
from citationclaw.skills.registry import build_default_registry


def test_all_new_skills_registered():
    reg = build_default_registry()
    assert reg.get("phase2_metadata") is not None
    assert reg.get("phase3_scholar_assess") is not None
    assert reg.get("phase4_citation_extract") is not None


def test_adapter_full_flow():
    """Full flow: flatten → enrich → convert → export-compatible."""
    adapter = PipelineAdapter()

    phase1 = {
        "page_0": {
            "paper_dict": {
                "paper_0": {
                    "paper_title": "Deep Learning for NLP",
                    "paper_link": "https://scholar.google.com/abc",
                    "paper_year": 2023,
                    "citation": "10",
                    "authors": {"author_0_Alice": "url1", "author_1_Bob": "url2"}
                },
                "paper_1": {
                    "paper_title": "Transformer Models",
                    "paper_link": "https://scholar.google.com/def",
                    "paper_year": 2022,
                    "citation": "5",
                    "authors": {"author_0_Carol": "url3"}
                }
            }
        }
    }

    papers = adapter.flatten_phase1_line(phase1)
    assert len(papers) == 2

    metadata = {
        "title": "Deep Learning for NLP",
        "authors": [
            {"name": "Alice", "affiliation": "MIT", "country": "US"},
            {"name": "Bob", "affiliation": "Google", "country": "US"},
        ],
        "sources": ["openalex"],
        "cited_by_count": 100,
    }

    record = adapter.to_legacy_record(
        paper=papers[0],
        metadata=metadata,
        self_citation={"is_self_citation": False, "method": "none"},
        renowned_scholars=[{"name": "Bob", "tier": "Industry Leader",
                           "honors": ["Google Researcher"], "affiliation": "Google"}],
        citing_paper="My Paper",
        record_index=1,
    )

    inner = record["1"]
    assert "Paper_Title" in inner
    assert "Searched Author-Affiliation" in inner
    assert "First_Author_Institution" in inner
    assert "Renowned Scholar" in inner
    assert "Formated Renowned Scholar" in inner
    assert "Citing_Paper" in inner
    assert "Data_Sources" in inner
    assert inner["Data_Sources"] == "openalex"


def test_prefilter_integrated():
    pf = ScholarPreFilter()
    assert pf.is_candidate({"name": "A", "h_index": 50, "citation_count": 0, "affiliation": ""})
    assert pf.is_candidate({"name": "B", "h_index": 5, "citation_count": 0, "affiliation": "MIT"})
    assert not pf.is_candidate({"name": "C", "h_index": 5, "citation_count": 0, "affiliation": "Random U"})


def test_self_citation_integrated():
    detector = SelfCitationDetector()
    result = detector.check(
        [{"name": "Alice Smith", "affiliation": "MIT"}],
        [{"name": "Alice Smith", "affiliation": "MIT"}, {"name": "Bob", "affiliation": "Google"}]
    )
    assert result["is_self_citation"] is True

    result2 = detector.check(
        [{"name": "Alice Smith", "affiliation": "MIT"}],
        [{"name": "Bob Jones", "affiliation": "Google"}]
    )
    assert result2["is_self_citation"] is False


def test_legacy_format_jsonl_roundtrip(tmp_path):
    """Verify legacy format records can be written to JSONL and read back."""
    adapter = PipelineAdapter()
    paper = {"paper_title": "Test", "paper_link": "http://x", "paper_year": 2023,
             "citation": "5", "page_id": "p0", "paper_id": "pp0", "authors_raw": {}}
    record = adapter.to_legacy_record(
        paper=paper, metadata={"authors": [], "sources": ["openalex"]},
        self_citation={"is_self_citation": False}, renowned_scholars=[],
        citing_paper="Target", record_index=1)

    jsonl_file = tmp_path / "test.jsonl"
    with open(jsonl_file, "w") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # Read back and verify format matches what Phase 3 export expects
    with open(jsonl_file) as f:
        line = f.readline()
        data = json.loads(line)
        assert "1" in data
        inner = data["1"]
        assert inner["Paper_Title"] == "Test"
        assert inner["Citing_Paper"] == "Target"
