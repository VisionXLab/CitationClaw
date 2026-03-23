import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from citationclaw.core.metadata_cache import MetadataCache


def test_cache_miss(tmp_path):
    cache = MetadataCache(cache_file=tmp_path / "test_cache.json")
    import asyncio
    result = asyncio.get_event_loop().run_until_complete(cache.get(title="nonexistent"))
    assert result is None
    assert cache.stats()["misses"] == 1


def test_cache_update_and_hit(tmp_path):
    import asyncio
    cache = MetadataCache(cache_file=tmp_path / "test_cache.json")
    loop = asyncio.get_event_loop()
    loop.run_until_complete(cache.update("10.1234", "Test Paper", {"title": "Test", "source": "openalex"}))
    loop.run_until_complete(cache.flush())
    result = loop.run_until_complete(cache.get(doi="10.1234"))
    assert result is not None
    assert result["title"] == "Test"
    assert "fetched_at" in result
    assert cache.stats()["hits"] == 1


def test_cache_persistence(tmp_path):
    import asyncio
    cache_file = tmp_path / "test_cache.json"
    cache1 = MetadataCache(cache_file=cache_file)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(cache1.update("", "persistent paper", {"title": "P", "source": "s2"}))
    loop.run_until_complete(cache1.flush())
    # Reload from disk
    cache2 = MetadataCache(cache_file=cache_file)
    result = loop.run_until_complete(cache2.get(title="persistent paper"))
    assert result is not None
    assert result["source"] == "s2"


def test_cache_key_normalization(tmp_path):
    import asyncio
    cache = MetadataCache(cache_file=tmp_path / "test_cache.json")
    loop = asyncio.get_event_loop()
    loop.run_until_complete(cache.update("", "My Paper Title", {"source": "openalex"}))
    result = loop.run_until_complete(cache.get(title="my paper title"))
    assert result is not None
