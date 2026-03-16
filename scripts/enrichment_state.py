"""
Enrichment state tracking — enables resume, daily rescans, and gap detection.

State is stored per source in data/enrichment-state.json. Each source tracks:
- last_scanned_slug: where the scan left off (alphabetical)
- scan_date: ISO date of last scan
- total_scanned: how many books have been checked
- total_matched: how many enrichments were found
- total_books: total books in collection at scan time

Usage:
    from enrichment_state import EnrichmentState
    state = EnrichmentState("gutenberg")
    state.should_scan("some-book-slug")  # True if not yet scanned today
    state.record_scan("some-book-slug", matched=True)
    state.save()
"""

import json
from datetime import date
from pathlib import Path

STATE_PATH = Path(__file__).parent.parent / "data" / "enrichment-state.json"


class EnrichmentState:
    def __init__(self, source: str) -> None:
        self.source = source
        self._all_state = self._load()
        if source not in self._all_state:
            self._all_state[source] = {
                "last_scanned_slug": "",
                "scan_date": "",
                "total_scanned": 0,
                "total_matched": 0,
                "total_books": 0,
            }
        self._state = self._all_state[source]

    def _load(self) -> dict:
        if STATE_PATH.exists():
            try:
                return json.loads(STATE_PATH.read_text())
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    @property
    def last_scanned_slug(self) -> str:
        return self._state.get("last_scanned_slug", "")

    @property
    def scan_date(self) -> str:
        return self._state.get("scan_date", "")

    @property
    def is_todays_scan(self) -> bool:
        return self.scan_date == date.today().isoformat()

    def should_scan(self, slug: str) -> bool:
        """Check if a book should be scanned (not yet reached in current scan).

        Always resumes from last_scanned_slug regardless of date.
        This prevents re-scanning already-processed books across sessions.
        """
        if not self.last_scanned_slug:
            return True  # Never scanned — start from beginning
        return slug > self.last_scanned_slug

    def record_scan(self, slug: str, matched: bool = False) -> None:
        """Record that a book was scanned."""
        self._state["last_scanned_slug"] = slug
        today = date.today().isoformat()
        # Reset daily counters on new day, but preserve last_scanned_slug
        if self._state.get("scan_date") != today:
            self._state["daily_scanned"] = 0
            self._state["daily_matched"] = 0
        self._state["scan_date"] = today
        self._state["total_scanned"] = self._state.get("total_scanned", 0) + 1
        self._state["daily_scanned"] = self._state.get("daily_scanned", 0) + 1
        if matched:
            self._state["total_matched"] = self._state.get("total_matched", 0) + 1
            self._state["daily_matched"] = self._state.get("daily_matched", 0) + 1

    def set_total_books(self, count: int) -> None:
        self._state["total_books"] = count

    def save(self) -> None:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(self._all_state, indent=2))

    @property
    def is_complete(self) -> bool:
        """True if scan has processed all books (across all sessions)."""
        total = self._state.get("total_books", 0)
        scanned = self._state.get("total_scanned", 0)
        return total > 0 and scanned >= total

    def reset(self) -> None:
        """Reset scan to start from the beginning (e.g., after new books added)."""
        self._state["last_scanned_slug"] = ""
        self._state["total_scanned"] = 0
        self._state["total_matched"] = 0
        self._state["daily_scanned"] = 0
        self._state["daily_matched"] = 0

    @staticmethod
    def load_all() -> dict:
        """Load the full state file for all sources."""
        if STATE_PATH.exists():
            try:
                return json.loads(STATE_PATH.read_text())
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def summary(self) -> str:
        s = self._state
        daily = f" (today: +{s.get('daily_scanned', 0)}/+{s.get('daily_matched', 0)})" if s.get('daily_scanned') else ""
        return (
            f"{self.source}: scanned={s['total_scanned']}, "
            f"matched={s['total_matched']}{daily}, "
            f"date={s['scan_date']}, "
            f"last={s['last_scanned_slug'][:30]}"
        )
