"""HTTP response cache for enrichment scripts.

Backs `data/http-cache.sqlite` with a single `responses` table keyed on
(source, key). Callers think in logical keys ("Plato", ISBN, OCLC id) so
URL-encoding drift doesn't cause cache misses for the same logical thing.

Usage:
    from http_cache import cached_fetch

    def _fetch():
        return safe_request(url)  # caller-supplied; may return None for 404

    data = cached_fetch(
        source="wikipedia",
        key=author_name,
        fetch=_fetch,
        ttl=7 * 86400,           # optional, falls back to per-source default
        negative_ttl=86400,      # optional, separate TTL for None / negatives
    )

Negative results (None) cache too, with their own shorter TTL — a 404
today might be a name-spelling fix tomorrow.

This module never imports urllib. Callers do their own HTTP. Keeps the
cache module trivially testable with a fake `fetch` closure.
"""

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable, Optional


DEFAULT_DB_PATH = Path(__file__).parent.parent / "data" / "http-cache.sqlite"

# Per-source TTL defaults, in seconds. Override per-call via `ttl=`.
DEFAULT_TTLS = {
    "wikipedia": 7 * 86400,        # bios change, but slowly
    "open_library": 30 * 86400,    # pretty stable
    "google_books": 30 * 86400,
    "gutenberg": 365 * 86400,      # public-domain catalog ~never changes
    "librivox": 30 * 86400,
    "hathitrust": 30 * 86400,
}
DEFAULT_FALLBACK_TTL = 7 * 86400
DEFAULT_NEGATIVE_TTL = 86400  # 24h — 404s should retry sooner than hits


_SCHEMA = """
CREATE TABLE IF NOT EXISTS responses (
  source        TEXT NOT NULL,
  key           TEXT NOT NULL,
  url           TEXT,
  status        INTEGER NOT NULL,
  body          BLOB,
  etag          TEXT,
  last_modified TEXT,
  fetched_at    INTEGER NOT NULL,
  expires_at    INTEGER NOT NULL,
  PRIMARY KEY (source, key)
);
CREATE INDEX IF NOT EXISTS idx_expires ON responses(expires_at);
"""


class Cache:
    """SQLite-backed cache. Use as a context manager or call .close() yourself."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        # WAL allows concurrent reads while a write is in flight — useful when
        # multiple enrichment scripts run in parallel.
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self) -> None:
        self.conn.close()

    def get(self, source: str, key: str, *, now: Optional[int] = None) -> tuple[bool, Any]:
        """Return (hit, value). value is the cached payload (None for negative).

        Returns (False, None) on miss or expiry. Caller must distinguish hit-with-None
        from miss using the `hit` boolean.
        """
        now = now if now is not None else int(time.time())
        row = self.conn.execute(
            "SELECT body, expires_at FROM responses WHERE source=? AND key=?",
            (source, key),
        ).fetchone()
        if row is None:
            return False, None
        body, expires_at = row
        if expires_at != 0 and expires_at <= now:
            return False, None
        if body is None:
            return True, None  # cached negative
        return True, json.loads(body.decode("utf-8"))

    def put(
        self,
        source: str,
        key: str,
        value: Any,
        *,
        ttl: int,
        url: Optional[str] = None,
        status: int = 200,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
        now: Optional[int] = None,
    ) -> None:
        now = now if now is not None else int(time.time())
        body = None if value is None else json.dumps(value, ensure_ascii=False).encode("utf-8")
        # ttl=0 is the sentinel for "never expires". Any other value (positive,
        # zero-relative, or negative) produces a real expires_at — negatives are
        # useful in tests to seed pre-expired rows.
        expires_at = 0 if ttl == 0 else now + ttl
        self.conn.execute(
            """
            INSERT INTO responses (source, key, url, status, body, etag, last_modified, fetched_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source, key) DO UPDATE SET
              url=excluded.url, status=excluded.status, body=excluded.body,
              etag=excluded.etag, last_modified=excluded.last_modified,
              fetched_at=excluded.fetched_at, expires_at=excluded.expires_at
            """,
            (source, key, url, status, body, etag, last_modified, now, expires_at),
        )
        self.conn.commit()

    def invalidate(self, source: str, key: Optional[str] = None) -> int:
        """Drop one row, or every row for a source if key is None. Returns rows deleted."""
        if key is None:
            cur = self.conn.execute("DELETE FROM responses WHERE source=?", (source,))
        else:
            cur = self.conn.execute(
                "DELETE FROM responses WHERE source=? AND key=?", (source, key)
            )
        self.conn.commit()
        return cur.rowcount

    def purge_expired(self, *, now: Optional[int] = None) -> int:
        """Remove rows past expiry. Returns rows deleted."""
        now = now if now is not None else int(time.time())
        cur = self.conn.execute(
            "DELETE FROM responses WHERE expires_at != 0 AND expires_at <= ?", (now,)
        )
        self.conn.commit()
        return cur.rowcount

    def stats(self) -> dict:
        """Return per-source row counts. Useful for runner status output."""
        rows = self.conn.execute(
            "SELECT source, COUNT(*) FROM responses GROUP BY source ORDER BY source"
        ).fetchall()
        total = self.conn.execute("SELECT COUNT(*) FROM responses").fetchone()[0]
        return {"total": total, "by_source": {s: c for s, c in rows}}


# ---------------------------------------------------------------------------
# Module-level convenience: a default singleton + cached_fetch().
# ---------------------------------------------------------------------------

_default_cache: Optional[Cache] = None


def _get_default_cache() -> Cache:
    global _default_cache
    if _default_cache is None:
        _default_cache = Cache()
    return _default_cache


def reset_default_cache(db_path: Path | str = DEFAULT_DB_PATH) -> Cache:
    """Drop the singleton and rebuild it (useful in tests)."""
    global _default_cache
    if _default_cache is not None:
        _default_cache.close()
    _default_cache = Cache(db_path)
    return _default_cache


def cached_fetch(
    source: str,
    key: str,
    fetch: Callable[[], Any],
    *,
    ttl: Optional[int] = None,
    negative_ttl: Optional[int] = None,
    cache: Optional[Cache] = None,
    url: Optional[str] = None,
) -> Any:
    """Look up (source, key); on miss, call `fetch()` and store the result.

    `fetch` returns the parsed payload (e.g. dict from JSON), or None to
    indicate "no result" (404, search returned nothing). Both kinds of
    answers cache, with separate TTLs.
    """
    c = cache if cache is not None else _get_default_cache()
    hit, value = c.get(source, key)
    if hit:
        return value

    value = fetch()

    if value is None:
        eff_ttl = negative_ttl if negative_ttl is not None else DEFAULT_NEGATIVE_TTL
    else:
        eff_ttl = ttl if ttl is not None else DEFAULT_TTLS.get(source, DEFAULT_FALLBACK_TTL)

    c.put(source, key, value, ttl=eff_ttl, url=url)
    return value


def invalidate(source: str, key: Optional[str] = None) -> int:
    return _get_default_cache().invalidate(source, key)


def purge_expired() -> int:
    return _get_default_cache().purge_expired()


def stats() -> dict:
    return _get_default_cache().stats()
