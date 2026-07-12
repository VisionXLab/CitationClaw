import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import asyncio
import json
import pytest
from citationclaw.skills.phase4_citation_extract import CitationExtractSkill


def test_skill_name():
    skill = CitationExtractSkill()
    assert skill.name == "phase4_citation_extract"


def test_read_jsonl(tmp_path):
    import json
    skill = CitationExtractSkill()
    jsonl_file = tmp_path / "test.jsonl"
    jsonl_file.write_text(
        json.dumps({"title": "Paper A"}) + "\n" +
        json.dumps({"title": "Paper B"}) + "\n"
    )
    papers = skill._read_jsonl(jsonl_file)
    assert len(papers) == 2
    assert papers[0]["title"] == "Paper A"


def test_has_run_method():
    skill = CitationExtractSkill()
    assert hasattr(skill, "run")
    assert callable(skill.run)


def test_s2_context_short_circuits_pdf_pipeline(tmp_path):
    skill = CitationExtractSkill()
    input_file = tmp_path / "merged.jsonl"
    output_file = tmp_path / "desc.jsonl"
    input_file.write_text(json.dumps({
        "1": {
            "Paper_Title": "Citing Paper",
            "Data_Sources": "s2_phase1",
            "s2_contexts": ["We build on the target method."],
            "s2_intents": ["methodology"],
            "s2_isInfluential": True,
        }
    }, ensure_ascii=False) + "\n", encoding="utf-8")

    class DummyConfig:
        openai_model = "unused"
        dashboard_model = "unused"

    class DummyCtx:
        config = DummyConfig()
        cancel_check = None
        progress = None

        @staticmethod
        def log(_message):
            return None

    result = asyncio.run(skill.run(
        DummyCtx(),
        input_file=input_file,
        output_file=output_file,
        target_title="Target",
    ))

    assert result.data["extracted"] == 1
    out = json.loads(output_file.read_text(encoding="utf-8").splitlines()[0])
    assert out["citing_desc_source"] == "s2"
    assert "target method" in out["Citing_Description"]


def test_s2_missing_context_does_not_use_pdf_pipeline(tmp_path):
    skill = CitationExtractSkill()
    input_file = tmp_path / "merged.jsonl"
    output_file = tmp_path / "desc.jsonl"
    input_file.write_text(json.dumps({
        "Paper_Title": "Citing Paper",
        "Data_Sources": "s2_phase1",
        "s2_contexts": [],
    }, ensure_ascii=False) + "\n", encoding="utf-8")

    class DummyConfig:
        openai_model = "unused"
        dashboard_model = "unused"

    class DummyCtx:
        config = DummyConfig()
        cancel_check = None
        progress = None

        @staticmethod
        def log(_message):
            return None

    result = asyncio.run(skill.run(
        DummyCtx(),
        input_file=input_file,
        output_file=output_file,
        target_title="Target",
    ))

    assert result.data["no_context"] == 1
    out = json.loads(output_file.read_text(encoding="utf-8").splitlines()[0])
    assert out["citing_desc_source"] == "s2_no_context"
    assert out["Citing_Description"] == "S2 未提供引用语境"


def test_mixed_context_priority_s2_cache_pdf_then_missing(tmp_path):
    skill = CitationExtractSkill()
    input_file = tmp_path / "merged.jsonl"
    output_file = tmp_path / "desc.jsonl"
    records = [
        {
            "Paper_Title": "S2 Paper",
            "Data_Sources": "s2_enrichment,openalex",
            "s2_contexts": ["S2 direct context."],
            "s2_intents": ["background"],
        },
        {
            "Paper_Title": "Cached Paper",
            "Paper_Link": "cache-link",
            "Data_Sources": "openalex",
        },
        {
            "Paper_Title": "PDF Paper",
            "Data_Sources": "openalex",
        },
        {
            "Paper_Title": "Missing Paper",
            "Data_Sources": "scholar",
        },
    ]
    input_file.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
        encoding="utf-8",
    )

    class DummyConfig:
        openai_model = "unused"
        dashboard_model = "unused"

    class DummyCtx:
        config = DummyConfig()
        cancel_check = None
        progress = None

        @staticmethod
        def log(_message):
            return None

    class DummyCache:
        def get(self, paper_link, _citing_title, _target_title):
            return "Cached description." if paper_link == "cache-link" else None

        async def update(self, *_args):
            return None

        async def flush(self):
            return None

    async def fake_get_contexts(
        _idx, paper, *_args, **_kwargs
    ):
        if paper["Paper_Title"] == "PDF Paper":
            return [{
                "section": "Related Work",
                "text": "PDF context.",
                "match_type": "direct",
            }]
        return []

    async def fake_llm_extract(*_args, **_kwargs):
        return "PDF description."

    skill._get_contexts = fake_get_contexts
    skill._llm_extract = fake_llm_extract

    result = asyncio.run(skill.run(
        DummyCtx(),
        input_file=input_file,
        output_file=output_file,
        target_title="Target",
        pdf_paths=["", "", "pdf-path", "pdf-path"],
        citation_desc_cache=DummyCache(),
    ))

    output_records = [
        json.loads(line)
        for line in output_file.read_text(encoding="utf-8").splitlines()
    ]
    assert [record["citing_desc_source"] for record in output_records] == [
        "s2",
        "cache",
        "pdf",
        "pdf_no_context",
    ]
    assert result.data["s2_context"] == 1
    assert result.data["cached"] == 1
    assert result.data["extracted"] == 2
    assert result.data["no_context"] == 1
