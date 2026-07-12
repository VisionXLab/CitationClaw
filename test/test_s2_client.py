import asyncio
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
import citationclaw.core.s2_client as s2_module
from citationclaw.core.s2_client import S2Client


class _FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class _FakeAsyncClient:
    def __init__(self, *, get_responses=None, post_responses=None):
        self.headers = {}
        self.get_responses = list(get_responses or [])
        self.post_responses = list(post_responses or [])
        self.header_snapshots = []

    async def get(self, *args, **kwargs):
        self.header_snapshots.append(dict(self.headers))
        return self.get_responses.pop(0)

    async def post(self, *args, **kwargs):
        self.header_snapshots.append(dict(self.headers))
        return self.post_responses.pop(0)

    async def aclose(self):
        pass

def test_build_search_url():
    client = S2Client()
    url = client._build_search_url("Attention is All You Need")
    assert "semanticscholar.org" in url
    assert "query" in url or "search" in url

def test_parse_paper_response():
    client = S2Client()
    mock_response = {
        "paperId": "P123",
        "title": "Attention is All You Need",
        "year": 2017,
        "citationCount": 100000,
        "influentialCitationCount": 5000,
        "authors": [
            {
                "authorId": "A1",
                "name": "Ashish Vaswani",
            }
        ],
        "externalIds": {"DOI": "10.xxxx"},
        "isOpenAccess": True,
        "openAccessPdf": {"url": "https://arxiv.org/pdf/1706.03762"},
    }
    result = client._parse_paper(mock_response)
    assert result["title"] == "Attention is All You Need"
    assert result["authors"][0]["name"] == "Ashish Vaswani"
    assert result["influential_citation_count"] == 5000
    assert result["source"] == "s2"

def test_parse_author_response():
    client = S2Client()
    mock_author = {
        "authorId": "A1",
        "name": "Ashish Vaswani",
        "hIndex": 30,
        "citationCount": 200000,
        "affiliations": ["Google Brain"],
    }
    result = client._parse_author(mock_author)
    assert result["name"] == "Ashish Vaswani"
    assert result["h_index"] == 30
    assert result["citation_count"] == 200000
    assert result["affiliation"] == "Google Brain"


def test_search_retries_anonymously_when_api_key_is_forbidden(monkeypatch):
    fake = _FakeAsyncClient(get_responses=[
        _FakeResponse(403),
        _FakeResponse(200, {"data": [{
            "paperId": "P123",
            "title": "Test Paper",
            "authors": [],
        }]}),
    ])
    monkeypatch.setattr(s2_module, "make_async_client", lambda **kwargs: fake)
    monkeypatch.setattr(s2_module, "_s2_global_sem", None)
    monkeypatch.setattr(s2_module.asyncio, "sleep", _no_sleep)

    client = S2Client(api_key="rejected-key")
    result = asyncio.run(client.search_paper("Test Paper"))

    assert result["s2_id"] == "P123"
    assert "x-api-key" in fake.header_snapshots[0]
    assert "x-api-key" not in fake.header_snapshots[1]
    assert client.used_anonymous_fallback is True
    assert client._rate_delay == 1.1


def test_batch_post_retries_anonymously_when_api_key_is_forbidden(monkeypatch):
    fake = _FakeAsyncClient(post_responses=[
        _FakeResponse(401),
        _FakeResponse(200, [{
            "paperId": "P123",
            "title": "Test Paper",
            "authors": [],
        }]),
    ])
    monkeypatch.setattr(s2_module, "make_async_client", lambda **kwargs: fake)
    monkeypatch.setattr(s2_module, "_s2_global_sem", None)
    monkeypatch.setattr(s2_module.asyncio, "sleep", _no_sleep)

    client = S2Client(api_key="rejected-key")
    result = asyncio.run(client.batch_papers(["P123"]))

    assert result["P123"]["title"] == "Test Paper"
    assert "x-api-key" in fake.header_snapshots[0]
    assert "x-api-key" not in fake.header_snapshots[1]
    assert client.used_anonymous_fallback is True


async def _no_sleep(_seconds):
    pass
