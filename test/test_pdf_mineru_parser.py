import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import io
import json
import zipfile

import pytest
from citationclaw.core.pdf_mineru_parser import MinerUParser


def test_extract_references():
    text = "Some text\n\nReferences\n[1] Paper A\n[2] Paper B"
    refs = MinerUParser._extract_references(text)
    assert "[1] Paper A" in refs
    assert "[2] Paper B" in refs


def test_extract_references_not_found():
    assert MinerUParser._extract_references("No refs here") == ""


def test_md_to_first_page():
    text = "Title\nAuthor Name\nUniversity\n\nAbstract text"
    blocks = MinerUParser._md_to_first_page(text)
    assert len(blocks) >= 3
    assert blocks[0]["text"] == "Title"
    assert blocks[0]["page_idx"] == 0


def test_paper_key():
    parser = MinerUParser()
    k1 = parser.paper_key({"doi": "10.1234/test"})
    k2 = parser.paper_key({"doi": "10.1234/test"})
    k3 = parser.paper_key({"doi": "10.5678/other"})
    assert k1 == k2  # same DOI -> same key
    assert k1 != k3  # different DOI -> different key


def test_normalize_page_grouped_content_list():
    raw = [
        [
            {
                "type": "title",
                "content": {
                    "title_content": [
                        {"type": "text", "content": "A Paper Title"}
                    ],
                    "level": 1,
                },
            },
            {
                "type": "paragraph",
                "content": {
                    "paragraph_content": [
                        {"type": "text", "content": "Alice and Bob"}
                    ]
                },
            },
        ],
        [
            {
                "type": "paragraph",
                "content": {
                    "paragraph_content": [
                        {"type": "text", "content": "Second page"}
                    ]
                },
            }
        ],
    ]

    normalized = MinerUParser._normalize_content_list(raw)

    assert [block["page_idx"] for block in normalized] == [0, 0, 1]
    assert normalized[0]["text"] == "A Paper Title"
    assert normalized[1]["text"] == "Alice and Bob"
    assert normalized[2]["text"] == "Second page"


def test_normalize_preserves_flat_content_list():
    raw = [
        {"type": "title", "text": "Flat Title", "page_idx": 0},
        {"type": "text", "text": "Page Two", "page_idx": 1},
    ]

    assert MinerUParser._normalize_content_list(raw) == raw


def test_extract_from_zip_accepts_page_grouped_content_list(tmp_path):
    raw_content = [[{
        "type": "title",
        "content": {
            "title_content": [{"type": "text", "content": "Paper Title"}],
            "level": 1,
        },
    }]]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("result/full.md", "# Paper Title\n\nAlice Example")
        archive.writestr("result/content_list.json", json.dumps(raw_content))

    result = MinerUParser()._extract_from_zip(buffer.getvalue(), tmp_path)

    assert result is not None
    assert result["source"] == "mineru_cloud_precision"
    assert result["first_page_blocks"][0]["text"] == "Paper Title"
    cached_content = json.loads((tmp_path / "content_list.json").read_text())
    assert cached_content[0]["page_idx"] == 0


def test_load_cached_accepts_existing_page_grouped_content_list(tmp_path):
    (tmp_path / "full.md").write_text("# Cached Paper\n\nCached Author")
    (tmp_path / "content_list.json").write_text(json.dumps([[{
        "type": "paragraph",
        "content": {
            "paragraph_content": [
                {"type": "text", "content": "Cached Author"}
            ]
        },
    }]]))
    (tmp_path / "meta.json").write_text(json.dumps({
        "source": "mineru_cloud_precision",
        "parsed_at": "2026-08-12T00:00:00+00:00",
    }))

    result = MinerUParser()._load_cached(tmp_path)

    assert result is not None
    assert result["source"] == "mineru_cloud_precision"
    assert result["first_page_blocks"][0]["text"] == "Cached Author"
