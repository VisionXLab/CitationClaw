import json

from citationclaw.skills.phase1_s2_citation_fetch import S2CitationFetchSkill


def test_s2_phase1_writer_outputs_compatible_jsonl(tmp_path):
    skill = S2CitationFetchSkill()
    output = tmp_path / "s2_citing.jsonl"
    seed = {
        "paperId": "S0",
        "title": "Target Paper",
        "year": 2020,
        "citationCount": 12,
    }
    light = [{
        "citingPaper": {
            "paperId": "C1",
            "title": "Citing Paper",
            "year": 2024,
            "citationCount": 7,
        }
    }]
    details = {
        "C1": {
            "paperId": "C1",
            "title": "Citing Paper",
            "year": 2024,
            "citationCount": 9,
            "influentialCitationCount": 2,
            "venue": "TestConf",
            "externalIds": {"DOI": "10.123/test", "ArXiv": "2401.00001"},
            "openAccessPdf": {"url": "https://arxiv.org/pdf/2401.00001"},
            "authors": [{"authorId": "A1", "name": "Alice Smith"}],
        }
    }
    contexts = {
        "C1": {
            "contexts": ["We build on Target Paper."],
            "intents": ["background"],
            "contextsWithIntent": [{"context": "We build on Target Paper.", "intents": ["background"]}],
            "isInfluential": True,
        }
    }

    written = skill._write_output(
        output_file=output,
        seed=seed,
        light_items=light,
        details=details,
        contexts=contexts,
        target_title="Target Paper",
    )

    assert written == 1
    data = json.loads(output.read_text(encoding="utf-8"))
    paper = data["page_0"]["paper_dict"]["paper_0"]
    assert paper["paper_title"] == "Citing Paper"
    assert paper["source"] == "s2"
    assert paper["s2_id"] == "C1"
    assert paper["citation"] == "9"
    assert paper["s2_contexts"] == ["We build on Target Paper."]
    assert paper["s2_metadata"]["sources"] == ["s2_phase1"]
