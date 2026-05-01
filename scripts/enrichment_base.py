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
from urllib.error import HTTPError, URLError
from urllib.request import urlopen, Request

from enrichment_config import BOOKS_DIR, USER_AGENT, DEFAULT_TIMEOUT, RATE_LIMITS, ERROR_LOG
from enrichment_state import EnrichmentState
from http_cache import cached_fetch


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
        """Underlying HTTP+JSON fetch. Same error semantics as before."""
        req = Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
                return json.loads(resp.read())
        except HTTPError as e:
            if e.code == 404:
                return None  # Not found — permanent, don't retry
            elif e.code == 429:
                self._log_error("rate_limited", url, str(e))
                return None  # Rate limited — skip for now
            else:
                self._log_error("http_error", url, f"HTTP {e.code}")
                return None
        except URLError as e:
            self._log_error("connection_error", url, str(e))
            return None
        except (json.JSONDecodeError, OSError) as e:
            self._log_error("parse_error", url, str(e))
            return None

    def save_book(self, book_path: Path, book: dict, new_fields: dict) -> bool:
        """Update book JSON with new fields. Only fills missing/empty fields.

        Special handling for _gutenberg_subjects: merges into subjects array.
        """
        changed = False

        # Handle special merge fields
        gutenberg_subjects = new_fields.pop("_gutenberg_subjects", None)
        if gutenberg_subjects:
            existing_subjects = set(book.get("subjects") or [])
            merged = sorted(existing_subjects | set(gutenberg_subjects))
            if merged != sorted(existing_subjects):
                book["subjects"] = merged
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
