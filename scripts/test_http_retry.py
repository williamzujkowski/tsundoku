"""Tests for http_retry — backoff, Retry-After parsing, network resilience."""

import io
import time
from email.utils import format_datetime
from datetime import datetime, timezone, timedelta
from urllib.error import HTTPError, URLError

import pytest

from http_retry import (
    RETRYABLE_STATUSES,
    _backoff_seconds,
    _retry_after_seconds,
    fetch_bytes,
    fetch_json,
    fetch_with_retry,
)


class _FakeHeaders(dict):
    """dict-like that mimics http.client.HTTPMessage's .get()."""


class TestRetryAfterParsing:
    def test_seconds_form(self):
        h = _FakeHeaders({"Retry-After": "5"})
        assert _retry_after_seconds(h) == 5.0

    def test_http_date_form(self):
        future = datetime.now(timezone.utc) + timedelta(seconds=10)
        h = _FakeHeaders({"Retry-After": format_datetime(future)})
        result = _retry_after_seconds(h)
        # Allow ±1s for clock slop
        assert 8.5 < result < 11.5

    def test_past_http_date_returns_zero(self):
        past = datetime.now(timezone.utc) - timedelta(seconds=10)
        h = _FakeHeaders({"Retry-After": format_datetime(past)})
        assert _retry_after_seconds(h) == 0.0

    def test_missing_returns_none(self):
        assert _retry_after_seconds(_FakeHeaders()) is None
        assert _retry_after_seconds(None) is None

    def test_garbage_returns_none(self):
        assert _retry_after_seconds(_FakeHeaders({"Retry-After": "not a date"})) is None


class TestBackoff:
    def test_increases_exponentially(self):
        # With jitter we get random-up-to, so test the cap on each attempt
        for _ in range(20):
            assert 0 <= _backoff_seconds(1) <= 2
            assert 0 <= _backoff_seconds(2) <= 4
            assert 0 <= _backoff_seconds(3) <= 8

    def test_caps(self):
        for _ in range(20):
            assert _backoff_seconds(20, cap=5.0) <= 5.0


class _FakeResponse:
    def __init__(self, body: bytes, status: int = 200, headers: dict | None = None):
        self._body = body
        self.status = status
        self.headers = headers or {}

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass


def _http_error(code: int, retry_after: str = None):
    headers = _FakeHeaders()
    if retry_after:
        headers["Retry-After"] = retry_after
    return HTTPError("http://x", code, "msg", headers, io.BytesIO(b""))


class TestFetchWithRetry:
    def test_success_first_try(self, monkeypatch):
        monkeypatch.setattr(
            "http_retry.urlopen",
            lambda req, timeout: _FakeResponse(b"ok", 200),
        )
        body, status, _headers = fetch_with_retry("http://x")
        assert body == b"ok"
        assert status == 200

    def test_404_no_retry(self, monkeypatch):
        calls = {"n": 0}

        def fake(req, timeout):
            calls["n"] += 1
            raise _http_error(404)

        monkeypatch.setattr("http_retry.urlopen", fake)
        body, status, _headers = fetch_with_retry("http://x", max_attempts=3)
        assert body is None
        assert status == 404
        assert calls["n"] == 1  # no retry on 404

    def test_429_then_success(self, monkeypatch):
        calls = {"n": 0}

        def fake(req, timeout):
            calls["n"] += 1
            if calls["n"] == 1:
                raise _http_error(429, retry_after="0")  # back off 0s
            return _FakeResponse(b"yay", 200)

        monkeypatch.setattr("http_retry.urlopen", fake)
        body, status, _headers = fetch_with_retry("http://x", max_attempts=3)
        assert body == b"yay"
        assert status == 200
        assert calls["n"] == 2

    def test_429_exhausts_attempts(self, monkeypatch):
        def fake(req, timeout):
            raise _http_error(429, retry_after="0")

        monkeypatch.setattr("http_retry.urlopen", fake)
        body, status, _headers = fetch_with_retry("http://x", max_attempts=2)
        assert body is None
        assert status == 429

    def test_503_treated_as_retryable(self, monkeypatch):
        calls = {"n": 0}

        def fake(req, timeout):
            calls["n"] += 1
            if calls["n"] == 1:
                raise _http_error(503, retry_after="0")
            return _FakeResponse(b"recovered", 200)

        monkeypatch.setattr("http_retry.urlopen", fake)
        body, _status, _headers = fetch_with_retry("http://x", max_attempts=3)
        assert body == b"recovered"

    def test_400_no_retry(self, monkeypatch):
        calls = {"n": 0}

        def fake(req, timeout):
            calls["n"] += 1
            raise _http_error(400)

        monkeypatch.setattr("http_retry.urlopen", fake)
        body, status, _headers = fetch_with_retry("http://x", max_attempts=3)
        assert body is None
        assert status == 400
        assert calls["n"] == 1

    def test_network_error_retries(self, monkeypatch):
        calls = {"n": 0}

        def fake(req, timeout):
            calls["n"] += 1
            if calls["n"] < 3:
                raise URLError("dns fail")
            return _FakeResponse(b"finally", 200)

        # Patch sleep so the backoff doesn't actually wait
        monkeypatch.setattr("http_retry.time.sleep", lambda s: None)
        monkeypatch.setattr("http_retry.urlopen", fake)
        body, _status, _headers = fetch_with_retry("http://x", max_attempts=4)
        assert body == b"finally"
        assert calls["n"] == 3

    def test_honors_retry_after(self, monkeypatch):
        slept = []

        def fake_sleep(s):
            slept.append(s)

        monkeypatch.setattr("http_retry.time.sleep", fake_sleep)

        calls = {"n": 0}

        def fake_open(req, timeout):
            calls["n"] += 1
            if calls["n"] == 1:
                raise _http_error(429, retry_after="3")
            return _FakeResponse(b"ok", 200)

        monkeypatch.setattr("http_retry.urlopen", fake_open)
        fetch_with_retry("http://x", max_attempts=2)
        assert slept == [3.0]


class TestFetchJson:
    def test_decodes(self, monkeypatch):
        monkeypatch.setattr(
            "http_retry.urlopen",
            lambda req, timeout: _FakeResponse(b'{"a": 1}', 200),
        )
        assert fetch_json("http://x") == {"a": 1}

    def test_returns_none_on_error(self, monkeypatch):
        monkeypatch.setattr("http_retry.urlopen", lambda req, timeout: _http_error(404).__class__)
        # Just hit the error path
        def fake(req, timeout):
            raise _http_error(404)
        monkeypatch.setattr("http_retry.urlopen", fake)
        assert fetch_json("http://x") is None

    def test_returns_none_on_invalid_json(self, monkeypatch):
        monkeypatch.setattr(
            "http_retry.urlopen",
            lambda req, timeout: _FakeResponse(b"not json", 200),
        )
        assert fetch_json("http://x") is None


class TestFetchBytes:
    def test_returns_body(self, monkeypatch):
        monkeypatch.setattr(
            "http_retry.urlopen",
            lambda req, timeout: _FakeResponse(b"raw bytes", 200),
        )
        assert fetch_bytes("http://x") == b"raw bytes"


def test_retryable_set_contents():
    assert 429 in RETRYABLE_STATUSES
    assert 503 in RETRYABLE_STATUSES
    assert 502 in RETRYABLE_STATUSES
    assert 200 not in RETRYABLE_STATUSES
    assert 404 not in RETRYABLE_STATUSES
