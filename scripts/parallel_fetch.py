"""Concurrent multi-source enrichment with per-source rate buckets.

The serial walk in enrich-authors-gaps.py / enrich-gaps.py spends most of
its wall time in `time.sleep()` between API calls. Each source has its own
rate budget, but our serial flow couples them so OL's quota stalls the
Wikipedia call. This module decouples them: each source gets a token-bucket
rate limiter, and source callables for one record fire concurrently
through a ThreadPoolExecutor. The bucket is shared across records so the
budget is honored even when many records are processed in parallel.

Usage:

    buckets = {
        "wikipedia": TokenBucket(rate_per_sec=5, burst=10),
        "open_library": TokenBucket(rate_per_sec=5, burst=10),
        "wikidata": TokenBucket(rate_per_sec=2, burst=4),
    }
    sources = [
        ("wikipedia", lambda: from_wikipedia(name=name)),
        ("open_library", lambda: from_open_library_author_page(name=name)),
        ("wikidata", lambda: from_wikidata(name=name)),
    ]
    results = parallel_sources(sources, buckets, executor)
    # results: {"wikipedia": {...}, "open_library": {...}, "wikidata": {...}}
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class TokenBucket:
    """Thread-safe token bucket rate limiter.

    `rate_per_sec` tokens are added per second up to `burst`. `acquire()`
    blocks until a token is available, then consumes one. Designed for
    request-per-second smoothing across worker threads sharing one
    upstream API budget.
    """

    rate_per_sec: float
    burst: float
    _tokens: float = field(init=False)
    _last_refill: float = field(init=False)
    _lock: threading.Lock = field(init=False, default_factory=threading.Lock)

    def __post_init__(self) -> None:
        self._tokens = float(self.burst)
        self._last_refill = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self.burst, self._tokens + elapsed * self.rate_per_sec)
        self._last_refill = now

    def acquire(self, tokens: float = 1.0) -> None:
        """Block until `tokens` are available, then consume them."""
        while True:
            with self._lock:
                self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return
                deficit = tokens - self._tokens
                wait = deficit / self.rate_per_sec
            # Sleep outside the lock so other threads can refill / acquire
            time.sleep(wait)


# Default budgets per source. Conservative — if we see 429s we lower these.
# Sources documented their own crawl-delays / public quotas where known.
DEFAULT_BUCKETS: dict[str, TokenBucket] = {
    "wikipedia": TokenBucket(rate_per_sec=5.0, burst=10),
    "open_library": TokenBucket(rate_per_sec=5.0, burst=10),
    "open_library_author": TokenBucket(rate_per_sec=5.0, burst=10),
    "open_library_editions": TokenBucket(rate_per_sec=5.0, burst=10),
    "wikidata": TokenBucket(rate_per_sec=2.0, burst=4),
    "wikidata_search": TokenBucket(rate_per_sec=2.0, burst=4),
    "wikidata_entity": TokenBucket(rate_per_sec=2.0, burst=4),
    "google_books": TokenBucket(rate_per_sec=1.0, burst=2),
}


SourceFn = Callable[[], dict]


def parallel_sources(
    sources: list[tuple[str, SourceFn]],
    buckets: dict[str, TokenBucket] | None = None,
    executor: ThreadPoolExecutor | None = None,
) -> dict[str, dict]:
    """Fire all source callables concurrently, gated by per-source buckets.

    `sources` is a list of (source_name, callable) pairs. The callable
    should be the result of binding any per-record arguments (closure).

    `buckets` maps source names to rate limiters. Sources without a bucket
    bypass rate limiting (use only for already-rate-limited sources).

    `executor` may be passed in to share a thread pool across many records;
    otherwise a one-shot pool sized to len(sources) is created.

    Returns a dict mapping each source name to whatever the callable
    returned (typically {} on miss/error). Exceptions inside source
    callables are caught and replaced with {} so one source failing
    doesn't kill the rest.
    """
    if buckets is None:
        buckets = DEFAULT_BUCKETS

    own_executor = executor is None
    if own_executor:
        executor = ThreadPoolExecutor(max_workers=max(1, len(sources)))

    futures: dict[str, Future] = {}
    try:
        for name, fn in sources:
            bucket = buckets.get(name)
            futures[name] = executor.submit(_with_bucket, bucket, fn)

        results: dict[str, dict] = {}
        for name, fut in futures.items():
            try:
                results[name] = fut.result() or {}
            except Exception:
                results[name] = {}
        return results
    finally:
        if own_executor:
            executor.shutdown(wait=True)


def _with_bucket(bucket: TokenBucket | None, fn: SourceFn) -> dict:
    if bucket is not None:
        bucket.acquire()
    try:
        return fn() or {}
    except Exception:
        return {}
