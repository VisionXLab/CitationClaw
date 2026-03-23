import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from citationclaw.core.pdf_parser import PDFCitationParser


def test_find_reference_id():
    parser = PDFCitationParser()
    text = """
Some paper text here.

References
[1] Smith et al. Some other paper. 2020.
[2] Alice Wang, Bob Jones. Attention is All You Need. NeurIPS 2017.
[3] Another reference here.
"""
    ref_id = parser._find_reference_id(text, "Attention is All You Need", ["Alice Wang"])
    assert ref_id == "[2]"


def test_find_reference_id_not_found():
    parser = PDFCitationParser()
    text = "No references section here."
    ref_id = parser._find_reference_id(text, "Nonexistent Paper", ["Nobody"])
    assert ref_id is None


def test_extract_contexts():
    parser = PDFCitationParser()
    text = """
1. Introduction
Transformers have revolutionized NLP. The seminal work [2] proposed the
attention mechanism that forms the backbone of modern language models.

2. Related Work
Several approaches build on [2] including BERT and GPT.

3. Method
Our method uses a standard transformer [1] architecture.

References
[1] Some other paper.
[2] Attention is All You Need.
"""
    contexts = parser._extract_contexts(text, "[2]", "Attention is All You Need")
    assert len(contexts) >= 2
    assert any("revolutionized" in c for c in contexts)


def test_detect_section():
    parser = PDFCitationParser()
    assert parser._detect_section("1. Introduction\nThis paper...") == "Introduction"
    assert parser._detect_section("Related Work\nSeveral...") == "Related Work"
    assert parser._detect_section("3 Method\nWe propose...") == "Method"
