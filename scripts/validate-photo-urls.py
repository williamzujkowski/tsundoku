#!/usr/bin/env python3
"""HEAD-probe every photo_url / cover_url and clear confirmed-dead ones.

Usage:
  python scripts/validate-photo-urls.py            # dry-run report only
  python scripts/validate-photo-urls.py --apply    # actually clear dead URLs
  python scripts/validate-photo-urls.py --limit 50 # limit for sampling

Goes through the http_cache layer (#91) so re-runs within the negative TTL
don't hammer Wikimedia. Negative TTL is shorter (24h) than positive TTL
(7d) — a 404 today might be a name-spelling fix tomorrow.

Only clears a URL when the probe returns 4xx (confirmed dead). Network
errors / timeouts / 5xx leave the URL alone and will retry next run.
"""

import argparse
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen, Request

sys.path.insert(0, str(Path(__file__).parent))

from enrichment_config import AUTHORS_DIR, BOOKS_DIR, USER_AGENT
from http_cache import cached_fetch
from json_merge import save_json


HEAD_TIMEOUT = 10  # seconds — should be plenty for a HEAD


def head_probe(url: str) -> dict | None:
    """Single HEAD request. Returns:
      {'status': int, 'ok': bool}  for definitive HTTP responses
      None                          for transient errors (429 rate limit,
                                    5xx, network blip, timeout) — caller
                                    treats as unknown and retries later

    Definitive 4xx (404, 410, 401, 403) → ok=False (clear the URL).
    Transient (429, 5xx) → None (don't draw any conclusion).
    """
    req = Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=HEAD_TIMEOUT) as resp:
            return {"status": resp.status, "ok": resp.status < 400}
    except HTTPError as e:
        # 429 = rate limited; 5xx = server hiccup. Both are NOT proof the URL
        # is dead — treat as unknown so we don't wrongly clear good URLs when
        # the upstream is just having a moment.
        if e.code == 429 or 500 <= e.code < 600:
            return None
        # Genuine 4xx (404, 410, 401, 403) — cache as confirmed dead.
        return {"status": e.code, "ok": False}
    except (URLError, TimeoutError, OSError):
        return None  # Network blip — don't cache; retry next run


def probe(url: str, source: str = "photo-validator-v2") -> dict | None:
    """Cache-aware HEAD probe. Cache key is the URL itself.

    Source name bumped to v2 when we changed head_probe to return None for
    429/5xx — old cache entries had ok=False for 429, which would still
    misclassify rate-limited URLs as dead.
    """
    return cached_fetch(source, url, lambda: head_probe(url), url=url)


def iter_records(target: str):
    """Yield (path, json_dict, url_field, url_value) for every record with a URL."""
    if target in ("authors", "all"):
        for p in sorted(AUTHORS_DIR.glob("*.json")):
            d = json.loads(p.read_text(encoding="utf-8"))
            if d.get("photo_url"):
                yield p, d, "photo_url", d["photo_url"]

    if target in ("books", "all"):
        for p in sorted(BOOKS_DIR.glob("*.json")):
            d = json.loads(p.read_text(encoding="utf-8"))
            for field in ("cover_url", "cover_url_large"):
                if d.get(field):
                    yield p, d, field, d[field]


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate photo / cover URLs in source JSON")
    parser.add_argument(
        "--target",
        choices=("authors", "books", "all"),
        default="all",
        help="Which content collection to validate (default: all)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually clear confirmed-dead URLs in the source JSON. "
             "Without this flag, runs as dry-run reporting only.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Probe at most N records (useful for sampling, 0=all)",
    )
    args = parser.parse_args()

    n_total = 0
    n_ok = 0
    n_dead = 0
    n_unknown = 0
    cleared_paths: set[Path] = set()
    dirty: dict[Path, dict] = {}  # accumulate per-file edits before writing

    for path, doc, field, url in iter_records(args.target):
        if args.limit and n_total >= args.limit:
            break
        n_total += 1
        result = probe(url)

        if result is None:
            n_unknown += 1
            continue
        if result.get("ok"):
            n_ok += 1
            continue

        # Confirmed dead (4xx)
        n_dead += 1
        status = result.get("status", "?")
        print(f"  DEAD {status}: {path.name}::{field}  {url[:80]}")

        if args.apply:
            doc = dirty.setdefault(path, doc)
            doc[field] = None  # null-out; load_existing in next enrichment will see it as empty
            cleared_paths.add(path)

    if args.apply and dirty:
        for path, doc in dirty.items():
            # Strip null values so the on-disk JSON matches the schema (zod .optional() expects absent, not null)
            cleaned = {k: v for k, v in doc.items() if v is not None}
            save_json(path, cleaned)

    print(f"\nValidated {n_total} URLs.")
    print(f"  ✓ live:    {n_ok}")
    print(f"  ✗ dead:    {n_dead}{' — cleared' if args.apply else ' — would be cleared with --apply'}")
    print(f"  ?  unknown: {n_unknown} (network errors; will retry next run)")
    if args.apply:
        print(f"\nUpdated {len(cleared_paths)} JSON files.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
