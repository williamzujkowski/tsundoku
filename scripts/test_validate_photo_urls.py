"""Tests for validate-photo-urls.py — exercises the probe() cache wrapper and
the head_probe() classification, without hitting the network."""

import importlib.util
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(__file__))

# Module name has a hyphen, so import via spec.
_spec = importlib.util.spec_from_file_location(
    "validate_photo_urls",
    Path(__file__).parent / "validate-photo-urls.py",
)
validator = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(validator)

from http_cache import Cache


@pytest.fixture
def cache(tmp_path):
    """Per-test cache."""
    c = Cache(tmp_path / "cache.sqlite")
    yield c
    c.close()


class TestHeadProbeClassification:
    """The head_probe function maps real urlopen outcomes to a small dict."""

    def test_handles_http_error_404(self, monkeypatch):
        from urllib.error import HTTPError

        def fake_urlopen(*args, **kwargs):
            raise HTTPError("u", 404, "Not Found", {}, None)

        monkeypatch.setattr(validator, "urlopen", fake_urlopen)
        result = validator.head_probe("https://example.com/dead.jpg")
        assert result == {"status": 404, "ok": False}

    def test_handles_url_error_returns_none(self, monkeypatch):
        from urllib.error import URLError

        def fake_urlopen(*args, **kwargs):
            raise URLError("DNS fail")

        monkeypatch.setattr(validator, "urlopen", fake_urlopen)
        result = validator.head_probe("https://nope.invalid/x.jpg")
        assert result is None  # Network errors don't get cached

    def test_handles_timeout_returns_none(self, monkeypatch):
        def fake_urlopen(*args, **kwargs):
            raise TimeoutError("slow")

        monkeypatch.setattr(validator, "urlopen", fake_urlopen)
        result = validator.head_probe("https://example.com/slow.jpg")
        assert result is None

    def test_handles_429_rate_limit_returns_none(self, monkeypatch):
        """429 is rate-limit, not 'URL is dead'. Must not get cleared."""
        from urllib.error import HTTPError

        def fake_urlopen(*args, **kwargs):
            raise HTTPError("u", 429, "Too Many Requests", {}, None)

        monkeypatch.setattr(validator, "urlopen", fake_urlopen)
        assert validator.head_probe("https://example.com/x.jpg") is None

    def test_handles_503_server_error_returns_none(self, monkeypatch):
        """5xx is transient, not definitive."""
        from urllib.error import HTTPError

        def fake_urlopen(*args, **kwargs):
            raise HTTPError("u", 503, "Service Unavailable", {}, None)

        monkeypatch.setattr(validator, "urlopen", fake_urlopen)
        assert validator.head_probe("https://example.com/x.jpg") is None

    def test_410_gone_is_definitive_dead(self, monkeypatch):
        """410 is the same as 404 for our purposes — definitively dead."""
        from urllib.error import HTTPError

        def fake_urlopen(*args, **kwargs):
            raise HTTPError("u", 410, "Gone", {}, None)

        monkeypatch.setattr(validator, "urlopen", fake_urlopen)
        result = validator.head_probe("https://example.com/x.jpg")
        assert result == {"status": 410, "ok": False}


class TestProbeCacheBehavior:
    """The cache layer should make repeat probes cheap."""

    def test_repeated_probe_uses_cache(self, cache, monkeypatch):
        """A live probe is called once; subsequent calls return from cache."""
        calls = []

        def fake_head(url):
            calls.append(url)
            return {"status": 200, "ok": True}

        monkeypatch.setattr(validator, "head_probe", fake_head)
        # Use the cache fixture explicitly — pass it through cached_fetch.
        from http_cache import cached_fetch

        for _ in range(3):
            cached_fetch(
                "photo-validator-test",
                "https://example.com/x.jpg",
                lambda: fake_head("https://example.com/x.jpg"),
                cache=cache,
            )
        assert calls == ["https://example.com/x.jpg"]  # exactly one network call

    def test_dead_url_caches_negative(self, cache, monkeypatch):
        """A 4xx response is itself the answer; second call shouldn't re-probe."""
        calls = []

        def fake_head(url):
            calls.append(url)
            return {"status": 404, "ok": False}

        from http_cache import cached_fetch

        cached_fetch(
            "photo-validator-test",
            "https://example.com/dead.jpg",
            lambda: fake_head("https://example.com/dead.jpg"),
            cache=cache,
        )
        cached_fetch(
            "photo-validator-test",
            "https://example.com/dead.jpg",
            lambda: fake_head("https://example.com/dead.jpg"),
            cache=cache,
        )
        # 4xx caches as the actual returned dict (truthy); fetch invoked once.
        assert len(calls) == 1


class TestApplyMode:
    """Smoke-test the actual CLI flow against a temp content tree."""

    def test_apply_clears_dead_url_in_author_json(self, tmp_path, monkeypatch):
        # Build a fake authors directory with one author whose photo_url is dead.
        authors_dir = tmp_path / "authors"
        authors_dir.mkdir()
        author_file = authors_dir / "test-author.json"
        author_file.write_text(
            '{"name": "Test Author", "slug": "test-author", "book_count": 1, "photo_url": "https://dead.example/x.jpg", "bio": "kept"}'
        )

        # Reroute the validator's directories and HEAD probe.
        monkeypatch.setattr(validator, "AUTHORS_DIR", authors_dir)
        monkeypatch.setattr(validator, "BOOKS_DIR", tmp_path / "no-books")

        def fake_head_probe(url):
            return {"status": 404, "ok": False}

        monkeypatch.setattr(validator, "head_probe", fake_head_probe)

        # Use a fresh cache so test runs are isolated.
        from http_cache import reset_default_cache

        reset_default_cache(tmp_path / "cache.sqlite")

        # Run --apply.
        monkeypatch.setattr(sys, "argv", ["validate-photo-urls.py", "--apply"])
        rc = validator.main()
        assert rc == 0

        # photo_url should be gone; bio should be preserved.
        import json

        result = json.loads(author_file.read_text())
        assert "photo_url" not in result
        assert result["bio"] == "kept"
        assert result["name"] == "Test Author"  # other fields preserved

    def test_dry_run_does_not_modify_files(self, tmp_path, monkeypatch):
        authors_dir = tmp_path / "authors"
        authors_dir.mkdir()
        original = '{"name": "Test", "slug": "test", "book_count": 1, "photo_url": "https://dead.example/x.jpg"}'
        author_file = authors_dir / "test.json"
        author_file.write_text(original)

        monkeypatch.setattr(validator, "AUTHORS_DIR", authors_dir)
        monkeypatch.setattr(validator, "BOOKS_DIR", tmp_path / "no-books")
        monkeypatch.setattr(validator, "head_probe", lambda u: {"status": 404, "ok": False})

        from http_cache import reset_default_cache

        reset_default_cache(tmp_path / "cache.sqlite")

        # No --apply.
        monkeypatch.setattr(sys, "argv", ["validate-photo-urls.py"])
        rc = validator.main()
        assert rc == 0

        # File untouched.
        assert author_file.read_text() == original
