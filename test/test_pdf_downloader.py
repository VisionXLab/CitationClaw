"""Tests for PDF downloader."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from citationclaw.core.pdf_downloader import (
    PDFDownloader, _transform_url, _extract_pdf_url_from_html, _build_cvf_candidates,
    _detect_publisher, _publisher_from_doi,
)


def test_cache_path(tmp_path):
    dl = PDFDownloader(cache_dir=tmp_path)
    paper = {"doi": "10.1234/test"}
    path = dl._cache_path(paper)
    assert path.parent == tmp_path
    assert path.suffix == ".pdf"


def test_cache_path_title_fallback(tmp_path):
    dl = PDFDownloader(cache_dir=tmp_path)
    paper = {"title": "My Paper Title"}
    path = dl._cache_path(paper)
    assert path.suffix == ".pdf"


def test_init_without_slow_fallback_config(tmp_path):
    dl = PDFDownloader(cache_dir=tmp_path)
    assert dl._scraper_keys == []
    assert dl._llm_key == ""
    assert dl._llm_base_url == ""
    assert dl._llm_model == ""


def test_publisher_detection_helpers():
    assert _detect_publisher("https://ieeexplore.ieee.org/document/123") == "ieee"
    assert _detect_publisher("https://www.sciencedirect.com/science/article/pii/S123") == "elsevier"
    assert _detect_publisher("https://dl.acm.org/doi/10.1145/123") == "acm"
    assert _detect_publisher("https://link.springer.com/article/10.1007/test") == "springer"
    assert _detect_publisher("https://onlinelibrary.wiley.com/doi/10.1002/test") == "wiley"
    assert _detect_publisher("https://openreview.net/forum?id=abc") == "unknown"
    assert _publisher_from_doi("10.1109/test") == "ieee"
    assert _publisher_from_doi("10.1016/j.test") == "elsevier"
    assert _publisher_from_doi("10.1145/123") == "acm"
    assert _publisher_from_doi("10.1007/test") == "springer"
    assert _publisher_from_doi("10.1002/test") == "wiley"
    assert _publisher_from_doi("10.48550/arXiv.1234") == "unknown"


def test_transform_url_cvf():
    url = "https://openaccess.thecvf.com/content/CVPR2025/html/Author_Title_CVPR_2025_paper.html"
    result = _transform_url(url)
    assert "/papers/" in result
    assert result.endswith("_paper.pdf")


def test_transform_url_openreview():
    url = "https://openreview.net/forum?id=abc123"
    assert _transform_url(url) == "https://openreview.net/pdf?id=abc123"


def test_transform_url_arxiv():
    url = "https://arxiv.org/abs/2505.12345"
    assert _transform_url(url) == "https://arxiv.org/pdf/2505.12345"


def test_transform_url_ieee():
    url = "https://ieeexplore.ieee.org/abstract/document/10804848/"
    result = _transform_url(url)
    assert "stamp.jsp" in result
    assert "10804848" in result


def test_transform_url_springer():
    url = "https://link.springer.com/article/10.1007/s12345-025-00001-2"
    result = _transform_url(url)
    assert "/content/pdf/" in result
    assert result.endswith(".pdf")


def test_transform_url_mdpi():
    url = "https://www.mdpi.com/1424-8220/25/1/65"
    assert _transform_url(url).endswith("/pdf")


def test_transform_url_sciencedirect():
    url = "https://www.sciencedirect.com/science/article/pii/S1566253525001234"
    assert "/pdfft" in _transform_url(url)


def test_transform_url_acl():
    url = "https://aclanthology.org/2024.acl-main.123"
    assert _transform_url(url).endswith(".pdf")


def test_extract_pdf_from_ieee_html():
    html = '<script>var xplGlobal={"pdfUrl":"/stamp/stamp.jsp?tp=&arnumber=123"}</script>'
    result = _extract_pdf_url_from_html(html, "https://ieeexplore.ieee.org/document/123")
    assert result is not None
    assert "stamp" in result


def test_extract_pdf_from_meta_tag():
    html = '<meta name="citation_pdf_url" content="https://example.com/paper.pdf">'
    result = _extract_pdf_url_from_html(html, "https://example.com")
    assert result == "https://example.com/paper.pdf"


def test_build_cvf_candidates():
    urls = _build_cvf_candidates("10.1109/cvpr.2025.123", "CVPR", 2025, "My Paper Title", "Smith")
    assert len(urls) >= 1
    assert "openaccess.thecvf.com" in urls[0]
    assert "CVPR2025" in urls[0]


def test_build_cvf_no_match():
    urls = _build_cvf_candidates("10.1234/other", "ICML", 2025, "Title", "Author")
    assert len(urls) == 0  # ICML is not CVF
