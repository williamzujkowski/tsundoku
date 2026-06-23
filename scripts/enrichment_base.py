"""
Shared base class for all enrichment scripts (Template Method pattern).

Subclasses implement:
  - source_name: str property
  - enrichment_field: str property (field to check for skip)
  - search(book: dict) -> dict | None (source-specific API call)

Base class handles:
  - Book loading and filtering
  - State tracking (resume, daily reset)
  - Progress reporting
  - Rate limiting
  - Error classification and logging
  - JSON file writes (only fill missing fields)
"""

import json
import time
import datetime
from abc import ABC, abstractmethod
from pathlib import Path

from enrichment_config import BOOKS_DIR, USER_AGENT, DEFAULT_TIMEOUT, RATE_LIMITS, ERROR_LOG
from enrichment_state import EnrichmentState
from http_cache import cached_fetch
from http_retry import fetch_with_retry
from deadletter import write_deadletter


class EnrichmentScript(ABC):
    """Base class for all enrichment scripts."""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Unique source identifier (e.g., 'gutenberg', 'librivox')."""
        ...

    @property
    @abstractmethod
    def enrichment_field(self) -> str:
        """Primary field to check — books with this field are skipped."""
        ...

    @abstractmethod
    def search(self, book: dict) -> dict | None:
        """Search the source for this book. Return dict of fields to add, or None."""
        ...

    @property
    def rate_limit(self) -> float:
        return RATE_LIMITS.get(self.source_name, 1.0)

    def load_books(self) -> list[tuple[Path, dict]]:
        """Load all book JSON files."""
        result = []
        for bp in sorted(BOOKS_DIR.glob("*.json")):
            result.append((bp, json.loads(bp.read_text())))
        return result

    def filter_unenriched(self, books: list[tuple[Path, dict]]) -> list[tuple[Path, dict]]:
        """Filter to books missing the enrichment field."""
        return [(bp, b) for bp, b in books if not b.get(self.enrichment_field)]

    def safe_request(self, url: str, *, cache_key: str | None = None) -> dict | None:
        """Make an HTTP request with error classification.

        Goes through the on-disk cache (data/http-cache.sqlite) keyed on
        (source_name, cache_key). Caller may pass a logical cache_key (e.g.
        an ISBN, OCLC id, or normalized title); falls back to the URL when
        omitted, which is the conservative default for callers that haven't
        been migrated yet.
        """
        key = cache_key if cache_key is not None else url
        return cached_fetch(self.source_name, key, lambda: self._raw_request(url), url=url)

    def _raw_request(self, url: str) -> dict | None:
        """Underlying HTTP+JSON fetch with 429/502/503/504 backoff + retry.

        Routes through ``http_retry.fetch_with_retry``, which honors
        ``Retry-After`` and applies exponential backoff with jitter on
        transient statuses instead of silently swallowing them.

        Return contract is unchanged for callers: a parsed JSON object
        (the truthy payload they index into) on success, or ``None`` on any
        failure — 404, non-retryable 4xx, retries exhausted, network error,
        or unparseable body. Permanent failures are recorded both to the
        legacy error log and to the dead-letter log so a re-run can target
        the lost set.
        """
        body, status, _headers = fetch_with_retry(
            url,
            user_agent=USER_AGENT,
            timeout=DEFAULT_TIMEOUT,
        )

        if body is not None:
            try:
                return json.loads(body)
            except (json.JSONDecodeError, ValueError) as e:
                self._log_error("parse_error", url, str(e))
                self._deadletter(url, status, "parse_error", str(e))
                return None

        # body is None -> permanent failure of some kind. Classify by status.
        if status == 404:
            error_type = "not_found"
        elif status == 0:
            error_type = "connection_error"
        elif status in (429, 502, 503, 504):
            # Transient class, but fetch_with_retry exhausted its budget.
            error_type = "rate_limited" if status == 429 else "http_error"
        else:
            error_type = "http_error"

        self._log_error(error_type, url, f"HTTP {status}" if status else "no response")
        self._deadletter(url, status, error_type, f"HTTP {status}" if status else "no response")
        return None

    def _deadletter(self, url: str, status: int, error_type: str, message: str) -> None:
        """Record a permanently-failed request to the dead-letter log."""
        write_deadletter(
            source=self.source_name,
            url=url,
            status=status,
            error_type=error_type,
            message=message,
        )

    def save_book(self, book_path: Path, book: dict, new_fields: dict) -> bool:
        """Update book JSON with new fields. Only fills missing/empty fields.

        Special handling for _gutenberg_subjects: merges into subject_facet
        (the curated successor to the dropped `subjects` field).
        """
        changed = False

        gutenberg_subjects = new_fields.pop("_gutenberg_subjects", None)
        if gutenberg_subjects:
            existing = set(book.get("subject_facet") or [])
            merged = sorted(existing | set(gutenberg_subjects))
            if merged != sorted(existing):
                book["subject_facet"] = merged
                changed = True

        for key, val in new_fields.items():
            existing = book.get(key)
            if existing is None or existing == "" or existing == []:
                book[key] = val
                changed = True

        if changed:
            book_path.write_text(json.dumps(book, indent=2, ensure_ascii=False))
        return changed

    def run(self, limit: int = 0) -> None:
        """Main execution loop with state tracking and progress reporting."""
        state = EnrichmentState(self.source_name)
        all_books = self.load_books()
        state.set_total_books(len(all_books))

        unenriched = self.filter_unenriched(all_books)
        # Filter by state (resume from last position)
        candidates = [
            (bp, b) for bp, b in unenriched
            if state.should_scan(b.get("slug", ""))
        ]

        print(f"[{self.source_name}] {len(unenriched)} books without {self.enrichment_field}")
        if len(candidates) < len(unenriched):
            print(f"  Resuming from '{state.last_scanned_slug}' ({len(unenriched) - len(candidates)} already scanned today)")

        if limit > 0:
            candidates = candidates[:limit]

        found = 0
        for i, (bp, book) in enumerate(candidates, 1):
            title = book["title"][:50]
            print(f"[{i}/{len(candidates)}] {title}...", end=" ", flush=True)

            try:
                result = self.search(book)
            except Exception as e:
                self._log_error("search_error", title, str(e))
                print(f"✗ {e}")
                state.record_scan(book.get("slug", ""), matched=False)
                time.sleep(self.rate_limit)
                continue

            if result and self.save_book(bp, book, result):
                found += 1
                state.record_scan(book.get("slug", ""), matched=True)
                print(f"✓ {','.join(result.keys())}")
            else:
                state.record_scan(book.get("slug", ""), matched=False)
                print("—")

            time.sleep(self.rate_limit)

        state.save()
        print(f"\nDone: {found} enriched out of {len(candidates)} searched")
        print(state.summary())

    def _log_error(self, error_type: str, context: str, message: str) -> None:
        """Append error to audit log."""
        entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "source": self.source_name,
            "type": error_type,
            "context": context[:200],
            "message": message[:500],
        }
        try:
            ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
            with open(ERROR_LOG, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            pass  # Don't fail enrichment because of log write failure

    @classmethod
    def cli(cls) -> None:
        """Standard CLI entrypoint with --limit argument."""
        import argparse
        parser = argparse.ArgumentParser(description=f"Enrich books via {cls.__name__}")
        parser.add_argument("--limit", type=int, default=0, help="Max books to process (0=all)")
        args = parser.parse_args()
        cls().run(limit=args.limit)
