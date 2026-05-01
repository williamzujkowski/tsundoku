"""Tests for http_cache. Uses tmp_path for the SQLite DB and a fake fetch
closure (no urllib mocking) — the whole point of the closure API."""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from http_cache import Cache, cached_fetch, DEFAULT_NEGATIVE_TTL


@pytest.fixture
def cache(tmp_path):
    """Fresh Cache backed by a per-test SQLite file."""
    c = Cache(tmp_path / "cache.sqlite")
    yield c
    c.close()


@pytest.fixture
def counting_fetch():
    """A fake fetch closure that records call count and returns programmable values."""

    class Counter:
        calls = 0
        next_value = {"answer": 42}

        def __call__(self):
            self.calls += 1
            return self.next_value

    return Counter()


class TestHitMiss:
    def test_miss_calls_fetch_and_caches(self, cache, counting_fetch):
        result = cached_fetch("wikipedia", "Plato", counting_fetch, cache=cache)
        assert result == {"answer": 42}
        assert counting_fetch.calls == 1

    def test_hit_does_not_call_fetch_again(self, cache, counting_fetch):
        cached_fetch("wikipedia", "Plato", counting_fetch, cache=cache)
        cached_fetch("wikipedia", "Plato", counting_fetch, cache=cache)
        cached_fetch("wikipedia", "Plato", counting_fetch, cache=cache)
        assert counting_fetch.calls == 1

    def test_per_source_isolation(self, cache, counting_fetch):
        """Same key under two sources doesn't collide."""
        counting_fetch.next_value = {"src": "wiki"}
        a = cached_fetch("wikipedia", "Plato", counting_fetch, cache=cache)
        counting_fetch.next_value = {"src": "open_library"}
        b = cached_fetch("open_library", "Plato", counting_fetch, cache=cache)
        assert a == {"src": "wiki"}
        assert b == {"src": "open_library"}
        assert counting_fetch.calls == 2


class TestExpiry:
    def test_expired_row_triggers_refetch(self, cache):
        """Manually insert a row in the past and assert next call refetches."""
        # Seed an expired row
        past = int(time.time()) - 100
        cache.put("wikipedia", "Plato", {"old": True}, ttl=-1, now=past)
        # Sanity: row exists but is past-expiry
        hit, _ = cache.get("wikipedia", "Plato")
        assert not hit

        calls = []

        def fetch():
            calls.append(1)
            return {"new": True}

        result = cached_fetch("wikipedia", "Plato", fetch, cache=cache)
        assert result == {"new": True}
        assert len(calls) == 1


class TestNegativeCache:
    def test_none_caches_with_negative_ttl(self, cache):
        calls = []

        def fetch():
            calls.append(1)
            return None  # 404 / search returned nothing

        cached_fetch("wikipedia", "ZZZ Nonexistent", fetch, cache=cache)
        cached_fetch("wikipedia", "ZZZ Nonexistent", fetch, cache=cache)
        assert len(calls) == 1  # Second call hit the negative cache

    def test_distinguishes_negative_hit_from_miss(self, cache):
        """A cached None must be a HIT (returns None without calling fetch),
        not a MISS that re-runs the fetch."""
        cache.put("wikipedia", "Plato", None, ttl=DEFAULT_NEGATIVE_TTL)
        hit, value = cache.get("wikipedia", "Plato")
        assert hit is True
        assert value is None


class TestInvalidation:
    def test_invalidate_one_row(self, cache, counting_fetch):
        cached_fetch("wikipedia", "Plato", counting_fetch, cache=cache)
        cache.invalidate("wikipedia", "Plato")
        cached_fetch("wikipedia", "Plato", counting_fetch, cache=cache)
        assert counting_fetch.calls == 2

    def test_invalidate_whole_source(self, cache, counting_fetch):
        cached_fetch("wikipedia", "Plato", counting_fetch, cache=cache)
        cached_fetch("wikipedia", "Aristotle", counting_fetch, cache=cache)
        n = cache.invalidate("wikipedia")
        assert n == 2

    def test_invalidate_returns_zero_for_missing(self, cache):
        assert cache.invalidate("wikipedia", "DoesNotExist") == 0


class TestPurge:
    def test_purge_expired_clears_only_expired(self, cache):
        now = int(time.time())
        cache.put("wikipedia", "expired", {"x": 1}, ttl=-100, now=now)
        cache.put("wikipedia", "fresh", {"x": 2}, ttl=86400, now=now)
        n = cache.purge_expired(now=now)
        assert n == 1
        # Fresh row still readable
        hit, val = cache.get("wikipedia", "fresh")
        assert hit and val == {"x": 2}


class TestStats:
    def test_stats_reports_per_source_counts(self, cache, counting_fetch):
        cached_fetch("wikipedia", "Plato", counting_fetch, cache=cache)
        cached_fetch("wikipedia", "Aristotle", counting_fetch, cache=cache)
        cached_fetch("open_library", "Plato", counting_fetch, cache=cache)
        s = cache.stats()
        assert s["total"] == 3
        assert s["by_source"] == {"open_library": 1, "wikipedia": 2}


class TestPersistence:
    def test_data_survives_reopen(self, tmp_path):
        """Cache file persists across process-equivalent restarts."""
        path = tmp_path / "persist.sqlite"
        c1 = Cache(path)
        c1.put("wikipedia", "Plato", {"survives": True}, ttl=86400)
        c1.close()

        c2 = Cache(path)
        try:
            hit, val = c2.get("wikipedia", "Plato")
            assert hit and val == {"survives": True}
        finally:
            c2.close()
