"""Tests for MunicipalityCache."""

from pathlib import Path

import pytest

from nfse_mcp.sefin_nacional.municipality_cache import MunicipalityCache


@pytest.fixture
def cache(tmp_path: Path):
    return MunicipalityCache(cache_path=tmp_path / "municipality_cache.json")


class TestMunicipalityCache:
    def test_get_missing_returns_none(self, cache: MunicipalityCache):
        assert cache.get("5300108") is None

    def test_set_and_get(self, cache: MunicipalityCache):
        cache.set("5300108", status="not_enabled", error_code="E0039", source="api_probe")
        entry = cache.get("5300108")
        assert entry is not None
        assert entry.status == "not_enabled"
        assert entry.error_code == "E0039"
        assert entry.source == "api_probe"
        assert entry.last_checked is not None

    def test_is_enabled(self, cache: MunicipalityCache):
        assert cache.is_enabled("5300108") is None
        cache.set("5300108", status="enabled")
        assert cache.is_enabled("5300108") is True
        cache.set("5300108", status="not_enabled")
        assert cache.is_enabled("5300108") is False
        cache.set("5300108", status="not_conveniado")
        assert cache.is_enabled("5300108") is False

    def test_persistence(self, tmp_path: Path):
        cache_path = tmp_path / "municipality_cache.json"
        cache1 = MunicipalityCache(cache_path=cache_path)
        cache1.set("5300108", status="enabled")

        cache2 = MunicipalityCache(cache_path=cache_path)
        entry = cache2.get("5300108")
        assert entry is not None
        assert entry.status == "enabled"

    def test_clear(self, cache: MunicipalityCache):
        cache.set("5300108", status="enabled")
        assert cache.get("5300108") is not None
        cache.clear()
        assert cache.get("5300108") is None
