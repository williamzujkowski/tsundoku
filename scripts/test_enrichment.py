"""Tests for the enrichment infrastructure modules."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from enrichment_state import EnrichmentState
from enrichment_config import RATE_LIMITS, API_URLS, USER_AGENT


class TestEnrichmentConfig:
    def test_rate_limits_all_positive(self):
        for source, limit in RATE_LIMITS.items():
            assert limit > 0, f"Rate limit for {source} must be positive"

    def test_api_urls_all_https(self):
        for source, url in API_URLS.items():
            assert url.startswith("https://"), f"API URL for {source} must use HTTPS"

    def test_user_agent_not_empty(self):
        assert len(USER_AGENT) > 10


class TestEnrichmentState:
    def test_new_state_has_defaults(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            state_path = Path(f.name)
            f.write(b"{}")

        with patch("enrichment_state.STATE_PATH", state_path):
            state = EnrichmentState("test_source")
            assert state.last_scanned_slug == ""
            assert state.scan_date == ""
            assert state._state["total_scanned"] == 0
            assert state._state["total_matched"] == 0

        state_path.unlink()

    def test_record_scan_increments(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            state_path = Path(f.name)
            f.write(b"{}")

        with patch("enrichment_state.STATE_PATH", state_path):
            state = EnrichmentState("test_source")
            state.record_scan("book-a", matched=False)
            state.record_scan("book-b", matched=True)
            state.record_scan("book-c", matched=True)

            assert state._state["total_scanned"] == 3
            assert state._state["total_matched"] == 2
            assert state.last_scanned_slug == "book-c"

        state_path.unlink()

    def test_save_and_reload(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            state_path = Path(f.name)
            f.write(b"{}")

        with patch("enrichment_state.STATE_PATH", state_path):
            state = EnrichmentState("test_source")
            state.record_scan("book-a", matched=True)
            state.save()

            # Reload
            state2 = EnrichmentState("test_source")
            assert state2._state["total_matched"] == 1
            assert state2.last_scanned_slug == "book-a"

        state_path.unlink()

    def test_multiple_sources_independent(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            state_path = Path(f.name)
            f.write(b"{}")

        with patch("enrichment_state.STATE_PATH", state_path):
            s1 = EnrichmentState("gutenberg")
            s2 = EnrichmentState("librivox")
            s1.record_scan("book-a", matched=True)
            s2.record_scan("book-b", matched=False)

            assert s1._state["total_matched"] == 1
            assert s2._state["total_matched"] == 0

        state_path.unlink()

    def test_summary_format(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            state_path = Path(f.name)
            f.write(b"{}")

        with patch("enrichment_state.STATE_PATH", state_path):
            state = EnrichmentState("test")
            state.record_scan("slug", matched=True)
            summary = state.summary()
            assert "test:" in summary
            assert "scanned=1" in summary
            assert "matched=1" in summary

        state_path.unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
