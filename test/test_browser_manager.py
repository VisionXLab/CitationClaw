import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from citationclaw.core.browser_manager import BrowserManager, detect_system_proxy


def test_detect_system_proxy(monkeypatch):
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("https_proxy", raising=False)
    monkeypatch.delenv("http_proxy", raising=False)
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:7890")
    proxy = detect_system_proxy()
    assert proxy is not None
    assert "7890" in proxy["server"]


def test_detect_no_proxy(monkeypatch):
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("http_proxy", raising=False)
    monkeypatch.delenv("https_proxy", raising=False)
    proxy = detect_system_proxy()
    assert proxy is None


def test_browser_manager_init():
    bm = BrowserManager()
    assert bm._headless is True
    assert bm._browser is None


def test_build_search_query():
    bm = BrowserManager()
    query = bm._build_google_url("Andrew Ng Stanford Fellow")
    assert "google.com" in query
    assert "Andrew" in query
