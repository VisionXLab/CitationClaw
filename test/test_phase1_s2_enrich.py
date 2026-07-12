import json

from citationclaw.skills.phase1_s2_citation_fetch import S2CitationFetchSkill
from citationclaw.skills.phase1_s2_enrich import S2CitationEnrichSkill


def test_exact_matching_preserves_gs_records_and_order():
    skill = S2CitationEnrichSkill()
    helper = S2CitationFetchSkill()
    lines = [{
        "page_0": {
            "paper_dict": {
                "paper_0": {
                    "paper_title": "DOI Match",
                    "paper_link": "https://doi.org/10.1234/doi-match",
                    "paper_year": 2024,
                    "citation": "Cited by 10",
                    "authors": {"author_0_Alice": "gs-profile"},
                },
                "paper_1": {
                    "paper_title": "Arxiv Match",
                    "paper_link": "https://example.test/arxiv",
                    "gs_pdf_link": "https://arxiv.org/pdf/2401.00001",
                    "paper_year": 2023,
                    "citation": "Cited by 5",
                    "authors": {},
                },
                "paper_2": {
                    "paper_title": "Title: Exact Match!",
                    "paper_link": "https://example.test/title",
                    "paper_year": 2022,
                    "citation": "Cited by 2",
                    "authors": {},
                },
                "paper_3": {
                    "paper_title": "GS Only Paper",
                    "paper_link": "https://example.test/gs-only",
                    "paper_year": 2025,
                    "citation": "Cited by 1",
                    "authors": {},
                },
            }
        }
    }]
    light = [
        {"citingPaper": {"paperId": "S1", "title": "DOI Match"}},
        {"citingPaper": {"paperId": "S2", "title": "Arxiv Match"}},
        {"citingPaper": {"paperId": "S3", "title": "Title Exact Match"}},
        {"citingPaper": {"paperId": "S4", "title": "S2 Only Paper"}},
    ]
    details = {
        "S1": {
            "paperId": "S1",
            "title": "Different S2 Title",
            "externalIds": {"DOI": "10.1234/doi-match"},
            "authors": [],
        },
        "S2": {
            "paperId": "S2",
            "title": "Different Arxiv Title",
            "externalIds": {"ArXiv": "2401.00001"},
            "authors": [],
        },
        "S3": {
            "paperId": "S3",
            "title": "Title Exact Match",
            "externalIds": {},
            "authors": [],
        },
        "S4": {
            "paperId": "S4",
            "title": "S2 Only Paper",
            "externalIds": {},
            "authors": [],
        },
    }
    contexts = {
        "S1": {
            "contexts": ["Uses the target method."],
            "intents": ["methodology"],
            "isInfluential": True,
        }
    }

    indexes = skill._build_match_indexes(
        light_items=light,
        details=details,
        contexts=contexts,
        helper=helper,
    )
    stats = skill._annotate_lines(lines=lines, indexes=indexes)
    papers = list(lines[0]["page_0"]["paper_dict"].values())

    assert stats == {
        "gs_total": 4,
        "matched": 3,
        "with_context": 1,
        "doi_exact": 1,
        "arxiv_exact": 1,
        "title_exact": 1,
        "unmatched": 1,
    }
    assert len(papers) == 4
    assert [paper["paper_title"] for paper in papers] == [
        "DOI Match",
        "Arxiv Match",
        "Title: Exact Match!",
        "GS Only Paper",
    ]
    assert papers[0]["citation"] == "Cited by 10"
    assert papers[0]["authors"]["author_0_Alice"] == "gs-profile"
    assert papers[0]["s2_contexts"] == ["Uses the target method."]
    assert papers[3]["s2_match_status"] == "unmatched"
    assert "s2_id" not in papers[3]


def test_fallback_copy_preserves_original_bytes(tmp_path):
    skill = S2CitationEnrichSkill()
    output = tmp_path / "output.jsonl"
    original = json.dumps(
        {"page_0": {"paper_dict": {"paper_0": {"paper_title": "GS"}}}},
        ensure_ascii=False,
    ) + "\n"

    skill._write_original(output, original)

    assert output.read_text(encoding="utf-8") == original
