"""HTTP fetch helpers with 429/503-aware backoff + retry.

Three of our enrichment sources rate-limit aggressively:
  * Wikimedia (Wikipedia REST + Commons FilePath via cache-photos.py)
  * Wikidata (SPARQL + EntityData)
  * Google Books (unauthenticated quota)

Without backoff, a hot loop loses 20–25% of requests during peak times.
This module wraps `urllib.request` with:

  - HTTP 429 / 503 detection
  - Honor Retry-After (seconds or HTTP-date)
  - Exponential backoff with full jitter (2s, 4s, 8s, …)
  - Configurable max attempts (default 3)
  - Returns (None, status) on permanent failures so callers can record
    them to the dead-letter log

Use the `fetch_json` / `fetch_bytes` convenience wrappers; they pull the
project's standard User-Agent and timeout.
"""

from __future__ import annotations

import json
import logging
import random
import sys
import time
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).parent))
from enrichment_config import USER_AGENT


DEFAULT_TIMEOUT = 20
DEFAULT_MAX_ATTEMPTS = 3
RETRYABLE_STATUSES = frozenset({429, 502, 503, 504})

log = logging.getLogger(__name__)


def _retry_after_seconds(headers) -> Optional[float]:
    """Parse a Retry-After header (seconds-int or HTTP-date) into seconds-from-now."""
    raw = headers.get("Retry-After") if headers else None
    if not raw:
        return None
    raw = raw.strip()
    # Pure-integer seconds form
    if raw.isdigit():
        return float(raw)
    # HTTP-date form
    try:
        dt = parsedate_to_datetime(raw)
        if dt is None:
            return None
        delta = dt.timestamp() - time.time()
        return max(0.0, delta)
    except (TypeError, ValueError):
        return None


def _backoff_seconds(attempt: int, base: float = 2.0, cap: float = 60.0) -> float:
    """Exponential backoff with full jitter. Attempt is 1-based."""
    expt = base * (2 ** (attempt - 1))
    return random.uniform(0, min(expt, cap))


def fetch_with_retry(
    url: str,
    *,
    user_agent: str = USER_AGENT,
    timeout: float = DEFAULT_TIMEOUT,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    extra_headers: Optional[dict] = None,
) -> Tuple[Optional[bytes], int, dict]:
    """Fetch a URL with automatic retry on transient errors.

    Returns (body_bytes, status_code, response_headers). On permanent
    failure (4xx other than 429, max attempts exhausted, network error
    after retries), returns (None, status_code, {}) where status_code is
    0 for network errors.

    On 404 returns (None, 404, {}) immediately — no retry, the resource
    just doesn't exist.
    """
    headers = {"User-Agent": user_agent}
    if extra_headers:
        headers.update(extra_headers)
    req = Request(url, headers=headers)

    last_status = 0
    for attempt in range(1, max_attempts + 1):
        try:
            with urlopen(req, timeout=timeout) as resp:
                return resp.read(), resp.status, dict(resp.headers)

        except HTTPError as e:
            last_status = e.code
            if e.code == 404:
                return None, 404, {}
            if e.code not in RETRYABLE_STATUSES or attempt == max_attempts:
                return None, e.code, {}
            # Honor Retry-After if the server gave one; else exponential jitter
            wait = _retry_after_seconds(e.headers) or _backoff_seconds(attempt)
            log.info("HTTP %s on %s — backing off %.1fs (attempt %d/%d)",
                     e.code, url, wait, attempt, max_attempts)
            time.sleep(wait)

        except (URLError, TimeoutError, OSError) as e:
            last_status = 0
            if attempt == max_attempts:
                return None, 0, {}
            wait = _backoff_seconds(attempt)
            log.info("Network error on %s: %s — backing off %.1fs (attempt %d/%d)",
                     url, e, wait, attempt, max_attempts)
            time.sleep(wait)

    return None, last_status, {}


def fetch_json(url: str, **kwargs) -> Optional[dict]:
    """fetch_with_retry → JSON-decoded payload, or None on miss/error."""
    body, _status, _headers = fetch_with_retry(url, **kwargs)
    if body is None:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def fetch_bytes(url: str, **kwargs) -> Optional[bytes]:
    """fetch_with_retry → raw bytes, or None on miss/error."""
    body, _status, _headers = fetch_with_retry(url, **kwargs)
    return body
