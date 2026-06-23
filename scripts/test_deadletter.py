"""Tests for the dead-letter writer and enrichment_base._raw_request routing.

_raw_request now goes through http_retry.fetch_with_retry (429/5xx backoff)
and records permanent failures to the dead-letter log. The return contract
for callers is unchanged: parsed JSON dict on success, None on any failure.
"""

import json

import pytest

import deadletter
from deadletter import write_deadletter
from enrichment_base import EnrichmentScript


class _Enricher(EnrichmentScript):
    """Minimal concrete subclass so we can exercise the base methods."""

    source_name = "testsource"
    enrichment_field = "test_field"

    def search(self, book):
        return None


# ---------------------------------------------------------------------------
# write_deadletter
# ---------------------------------------------------------------------------

class TestWriteDeadletter:
    def test_appends_valid_jsonl(self, tmp_path):
        log = tmp_path / "dl.jsonl"
        write_deadletter(
            source="gutenberg", url="http://x/1", status=429,
            error_type="rate_limited", message="HTTP 429", path=log,
        )
        write_deadletter(
            source="hathitrust", url="http://x/2", status=404,
            error_type="not_found", message="HTTP 404", path=log,
        )
        lines = log.read_text().splitlines()
        assert len(lines) == 2
        first = json.loads(lines[0])
        second = json.loads(lines[1])
        assert first["source"] == "gutenberg"
        assert first["status"] == 429
        assert first["error_type"] == "rate_limited"
        assert first["url"] == "http://x/1"
        assert "timestamp" in first
        assert second["error_type"] == "not_found"

    def test_creates_parent_dir(self, tmp_path):
        log = tmp_path / "nested" / "deeper" / "dl.jsonl"
        write_deadletter(
            source="s", url="http://x", status=0,
            error_type="connection_error", path=log,
        )
        assert log.exists()
        assert json.loads(log.read_text())["error_type"] == "connection_error"

    def test_never_raises_on_oserror(self, monkeypatch, tmp_path):
        # Point at a directory path so open() for append fails with OSError.
        bad = tmp_path  # a directory, not a file
        # Should swallow the error, not propagate.
        write_deadletter(
            source="s", url="http://x", status=500,
            error_type="http_error", path=bad,
        )

    def test_truncates_long_fields(self, tmp_path):
        log = tmp_path / "dl.jsonl"
        write_deadletter(
            source="s", url="http://x/" + "a" * 5000, status=500,
            error_type="http_error", message="b" * 5000, path=log,
        )
        rec = json.loads(log.read_text())
        assert len(rec["url"]) <= 1000
        assert len(rec["message"]) <= 500


# ---------------------------------------------------------------------------
# _raw_request routing
# ---------------------------------------------------------------------------

class TestRawRequestRetry:
    def test_success_returns_parsed_json(self, monkeypatch):
        monkeypatch.setattr(
            "enrichment_base.fetch_with_retry",
            lambda url, **kw: (b'{"results": [1, 2]}', 200, {}),
        )
        enr = _Enricher()
        result = enr._raw_request("http://x")
        assert result == {"results": [1, 2]}

    def test_retries_on_429_via_fetch_with_retry(self, monkeypatch):
        """_raw_request delegates retry to fetch_with_retry; on eventual
        success it returns parsed JSON and writes no dead-letter."""
        calls = {"n": 0}

        def fake_fetch(url, **kw):
            calls["n"] += 1
            # Simulate fetch_with_retry having internally retried past a 429
            # and ultimately succeeding — it returns a 200 body.
            return b'{"ok": true}', 200, {}

        dl_calls = []
        monkeypatch.setattr("enrichment_base.fetch_with_retry", fake_fetch)
        monkeypatch.setattr(
            "enrichment_base.write_deadletter",
            lambda **kw: dl_calls.append(kw),
        )
        enr = _Enricher()
        result = enr._raw_request("http://x")
        assert result == {"ok": True}
        assert calls["n"] == 1
        assert dl_calls == []  # success -> no dead-letter

    def test_uses_retryable_path_not_swallow(self, monkeypatch):
        """The old code swallowed 429 -> None with no retry. Now 429 must go
        through fetch_with_retry (which performs the backoff/retry)."""
        seen = {}

        def fake_fetch(url, **kw):
            seen["url"] = url
            seen["kw"] = kw
            return b'{"x": 1}', 200, {}

        monkeypatch.setattr("enrichment_base.fetch_with_retry", fake_fetch)
        _Enricher()._raw_request("http://api/thing")
        assert seen["url"] == "http://api/thing"


class TestRawRequestDeadLetter:
    @pytest.mark.parametrize("status,error_type", [
        (404, "not_found"),
        (0, "connection_error"),
        (429, "rate_limited"),
        (503, "http_error"),
        (502, "http_error"),
        (400, "http_error"),
        (500, "http_error"),
    ])
    def test_permanent_failure_returns_none_and_deadletters(
        self, monkeypatch, status, error_type
    ):
        monkeypatch.setattr(
            "enrichment_base.fetch_with_retry",
            lambda url, **kw: (None, status, {}),
        )
        dl_calls = []
        monkeypatch.setattr(
            "enrichment_base.write_deadletter",
            lambda **kw: dl_calls.append(kw),
        )
        # Don't actually touch the error log file.
        monkeypatch.setattr(EnrichmentScript, "_log_error", lambda *a, **k: None)

        enr = _Enricher()
        result = enr._raw_request("http://x")
        assert result is None
        assert len(dl_calls) == 1
        assert dl_calls[0]["source"] == "testsource"
        assert dl_calls[0]["status"] == status
        assert dl_calls[0]["error_type"] == error_type
        assert dl_calls[0]["url"] == "http://x"

    def test_unparseable_body_deadletters(self, monkeypatch):
        monkeypatch.setattr(
            "enrichment_base.fetch_with_retry",
            lambda url, **kw: (b"not json{", 200, {}),
        )
        dl_calls = []
        monkeypatch.setattr(
            "enrichment_base.write_deadletter",
            lambda **kw: dl_calls.append(kw),
        )
        monkeypatch.setattr(EnrichmentScript, "_log_error", lambda *a, **k: None)

        result = _Enricher()._raw_request("http://x")
        assert result is None
        assert dl_calls[0]["error_type"] == "parse_error"

    def test_end_to_end_writes_real_file(self, monkeypatch, tmp_path):
        """Full path: permanent failure -> real JSONL line on disk."""
        log = tmp_path / "dl.jsonl"
        monkeypatch.setattr(deadletter, "DEADLETTER_LOG", log)
        monkeypatch.setattr(
            "enrichment_base.fetch_with_retry",
            lambda url, **kw: (None, 429, {}),
        )
        monkeypatch.setattr(EnrichmentScript, "_log_error", lambda *a, **k: None)

        result = _Enricher()._raw_request("http://api/fail")
        assert result is None
        rec = json.loads(log.read_text().strip())
        assert rec["source"] == "testsource"
        assert rec["status"] == 429
        assert rec["error_type"] == "rate_limited"
