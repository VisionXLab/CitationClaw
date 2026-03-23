import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from citationclaw.core.pdf_downloader import PDFDownloader
from citationclaw.core.pdf_parser import PDFCitationParser


def test_downloader_and_parser_integration(tmp_path):
    """Integration test: verify downloader + parser work together."""
    dl = PDFDownloader(cache_dir=tmp_path)
    parser = PDFCitationParser()

    # Test with a fake cached PDF
    paper = {"title": "Test Paper", "doi": "10.test/fake"}
    cached_path = dl._cache_path(paper)

    # We can't actually download in unit tests, but verify the pipeline wiring
    assert cached_path.parent == tmp_path
    assert cached_path.suffix == ".pdf"

    # Verify parser handles missing fitz gracefully
    contexts = parser.extract_citation_contexts(
        cached_path, "Some Target Paper", ["Author A"]
    )
    # Should return empty list (no PDF to parse or fitz not installed)
    assert isinstance(contexts, list)


def test_parser_full_flow():
    """Test parser with synthetic text (no actual PDF needed)."""
    parser = PDFCitationParser()
    text = """
Abstract
We present a new approach to sequence modeling.

1. Introduction
The transformer architecture [1] has changed the field of NLP.
Building on Attention is All You Need [1], we propose improvements.

2. Related Work
Vaswani et al. [1] introduced the self-attention mechanism.
BERT [2] applied transformers to pre-training.

3. Method
We extend the standard transformer [1] with our novel layer.

References
[1] Ashish Vaswani et al. Attention is All You Need. NeurIPS 2017.
[2] Jacob Devlin et al. BERT. NAACL 2019.
"""
    ref_id = parser._find_reference_id(text, "Attention is All You Need", ["Vaswani"])
    assert ref_id == "[1]"

    contexts = parser._extract_contexts(text, ref_id, "Attention is All You Need")
    assert len(contexts) >= 2

    # Verify section detection
    for ctx in contexts:
        section = parser._detect_section(ctx)
        assert section in ["Introduction", "Related Work", "Method", "Abstract", "Unknown"]
