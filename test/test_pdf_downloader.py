import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from citationclaw.core.pdf_downloader import PDFDownloader


def test_determine_sources():
    dl = PDFDownloader()
    paper = {
        "title": "Test Paper",
        "doi": "10.1234/test",
        "pdf_url": "http://arxiv.org/pdf/2001.00001",
        "arxiv_id": "2001.00001",
    }
    sources = dl._determine_sources(paper)
    assert len(sources) > 0
    assert sources[0]["name"] == "arxiv"  # highest priority


def test_determine_sources_no_arxiv():
    dl = PDFDownloader()
    paper = {"title": "Test Paper", "doi": "10.1234/test"}
    sources = dl._determine_sources(paper)
    # Should still have unpaywall and doi-based sources
    assert any(s["name"] == "unpaywall" for s in sources)


def test_cache_path(tmp_path):
    dl = PDFDownloader(cache_dir=tmp_path)
    paper = {"title": "Test Paper", "doi": "10.1234/test"}
    path = dl._cache_path(paper)
    assert path.parent == tmp_path
    assert path.suffix == ".pdf"


def test_cache_hit(tmp_path):
    dl = PDFDownloader(cache_dir=tmp_path)
    paper = {"title": "Test Paper", "doi": "10.1234/test"}
    # Pre-create cached file
    cached = dl._cache_path(paper)
    cached.write_bytes(b"%PDF-1.4 fake content")
    import asyncio
    result = asyncio.get_event_loop().run_until_complete(dl.download(paper))
    assert result == cached
