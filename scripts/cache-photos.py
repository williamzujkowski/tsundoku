#!/usr/bin/env python3
"""Download author photos and book covers to public/cached/ for resilience.

After this script:
  - public/cached/authors/{slug}.{ext}  — local copy of each author photo
  - public/cached/covers/{slug}.{ext}   — local copy of each book cover
  - Source JSON's photo_url / cover_url / cover_url_large rewritten to
    local relative paths (e.g. "/tsundoku/cached/authors/plato.jpg")
  - Original upstream URLs preserved in photo_url_source / cover_url_source

If a download fails (404, network error), the original upstream URL is
LEFT IN PLACE — never blanked, never broken-by-this-script. Combined
with the runtime broken-image fallback in Layout.astro AND the build-time
existence guard (src/utils/imageGuard.ts / scripts/image_guard.py, #234's
companion fix), the site is "belt + suspenders" resilient to upstream rot.

Usage:
  python scripts/cache-photos.py                   # download all
  python scripts/cache-photos.py --target authors  # only authors
  python scripts/cache-photos.py --target books    # only books
  python scripts/cache-photos.py --limit 50        # sample
  python scripts/cache-photos.py --dry-run         # plan only, no writes

CI integration: this script runs in the prebuild step between content
sync and astro build. `public/cached/covers/` is gitignored —
actions/cache@v4 persists it across CI runs. `public/cached/authors/` is
DIFFERENT (#234): it's committed directly to the repo. Bulk re-fetching
author photos turned out to be structurally impossible for most of the
catalog — 1,092 of 1,542 stored Wikimedia URLs use a thumbnail format the
CDN now permanently rejects with HTTP 400, so no amount of CI
re-attempts would ever converge — while the photos themselves genuinely
never change once fetched. Since 1,538/1,542 were already downloaded (in
a prior session, before that Wikimedia policy took effect), committing
them outright is simpler and deterministic: `git checkout` puts them on
disk before this script even runs, `is_already_local()` + the existence
check below correctly report them as already-cached, and no network
round-trip happens for them ever again. This script's author path still
exists for: the ~349 authors with no known photo URL at all (a data gap,
not a caching one — nothing to do), the 4 in
KNOWN_UNFETCHABLE_AUTHOR_SLUGS below (skipped outright — see that
constant), and any newly-added author who doesn't yet have a
pre-committed photo.
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from http_retry import fetch_with_retry

sys.path.insert(0, str(Path(__file__).parent))

from enrichment_config import AUTHORS_DIR, BOOKS_DIR, USER_AGENT
from json_merge import save_json


REPO_ROOT = Path(__file__).parent.parent
PUBLIC_CACHED = REPO_ROOT / "public" / "cached"
ASTRO_BASE = "/tsundoku/"  # matches astro.config.mjs base — keep in sync

# Cached files are written to out_dir/{slug}.{ext}. Slugs are toSlug-generated
# (lowercase, hyphenated) everywhere, but the value is attacker-influenceable
# in principle (it flows from content JSON). Reject anything that could escape
# the cache directory before it reaches a filesystem path.
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

DOWNLOAD_TIMEOUT = 30  # seconds — covers can be a few hundred KB
SKIP_IF_NEWER_THAN_DAYS = 90  # don't re-download files newer than this

# Map of Content-Type → file extension
CONTENT_TYPE_EXT = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
    "image/svg+xml": "svg",
}

# Known-unfetchable author photos, confirmed via #234's investigation:
# genuinely-dead or permanently-rejected upstream URLs that no amount of
# retrying will ever fix. Documented here (with the reason) rather than
# silently skipped, so re-attempting them doesn't waste CI time forever,
# and so a future contributor who tracks down a replacement photo knows
# exactly which slugs to retire from this list once photo_url_source is
# fixed. All four remain in KNOWN_UNFETCHABLE_AUTHOR_SLUGS as of #234;
# most of the OTHER ~1,088 formerly-broken authors didn't need this list
# at all — they were simply committed to public/cached/authors/ directly
# (see #234), since the underlying photos were already downloaded (in a
# prior session, before Wikimedia's thumbnail-format change) and photos
# don't change, so re-fetching them was never actually necessary.
KNOWN_UNFETCHABLE_AUTHOR_SLUGS = frozenset({
    "anne-mccaffrey",   # HTTP 404 — upstream Wikimedia file no longer exists
    "terry-pratchett",  # HTTP 400 — old-style thumbnail URL, rejected by Wikimedia's CDN
    "hafez",            # HTTP 404 — upstream Wikimedia file no longer exists
    "malcolm-lowry",    # HTTP 404 — upstream Wikimedia file no longer exists
})


def is_already_local(url: str) -> bool:
    """True if the URL is already pointing into our local cache."""
    return url.startswith(ASTRO_BASE + "cached/") or url.startswith("/cached/")


def ext_from_response(content_type: str | None, url: str) -> str:
    """Pick a file extension from Content-Type header, falling back to URL suffix."""
    if content_type:
        primary = content_type.split(";")[0].strip().lower()
        if primary in CONTENT_TYPE_EXT:
            return CONTENT_TYPE_EXT[primary]
    # Fall back to last URL segment
    last_segment = url.rsplit("/", 1)[-1]
    if "." in last_segment:
        suffix = last_segment.rsplit(".", 1)[-1].lower()
        if suffix in {"jpg", "jpeg", "png", "webp", "gif", "svg"}:
            return "jpg" if suffix == "jpeg" else suffix
    return "jpg"  # safe default


# Records the most recent download() failure's HTTP status (0 = network
# error / no HTTP response at all) for the FAIL logs and the per-status
# summary breakdown below. A module-level side-channel rather than
# threading a new value through cache_one()'s existing (str, str) | None
# contract — safe because this script is single-threaded/sequential, so
# there's no concurrency hazard reading it immediately after each call.
# Added after the #234 incident investigation: cache-photos.py's FAIL
# lines previously gave no reason at all, which hid the actual root
# cause (see below) behind what looked like generic rate-limiting.
_last_fail_status: int = 0


def download(url: str) -> tuple[bytes, str] | None:
    """Fetch image bytes + extension, or None on failure.

    Goes through fetch_with_retry so 429/503 from Wikimedia and other
    rate-limiting CDNs auto-back-off and retry rather than dropping the
    record. Per a prior session, ~24% of cache-photos downloads were
    lost to silently-swallowed 429s.

    A large, distinct failure class discovered investigating #234: many
    stored Wikimedia URLs use the older path-based thumbnail form
    (".../thumb/x/xx/File.jpg/400px-File.jpg"), which Wikimedia's CDN now
    rejects outright with HTTP 400 ("Use thumbnail sizes listed on
    https://w.wiki/GHai") — regardless of retries, since the URL itself
    is permanently invalid, not rate-limited. The newer
    "Special:FilePath/File.jpg?width=400" form still works. That's a data
    fix (regenerating ~1,092 author photo URLs), tracked separately; this
    function's job is only to make the failure reason visible so it
    isn't mistaken for transient rate-limiting again.
    """
    global _last_fail_status
    body, status, headers = fetch_with_retry(url, timeout=DOWNLOAD_TIMEOUT)
    if body is None:
        _last_fail_status = status
        return None
    ext = ext_from_response(headers.get("Content-Type"), url)
    return body, ext


def cache_one(
    *,
    url: str,
    out_dir: Path,
    slug: str,
    rate_limit_s: float,
) -> tuple[str, str] | None:
    """Download `url` into `out_dir/{slug}.{ext}`. Returns (local_url, ext) or None.

    Tracks the source URL in a `<slug>.url` sidecar so that if a record's
    upstream URL is later edited (e.g. swapping a wrong Wikipedia
    thumbnail for an Open Library cover), the stale cached file is
    invalidated and re-fetched. Without this, the 90-day "skip if recent"
    optimisation reuses the previous URL's bytes silently — see the
    Cyberstorm regression where the 1996 video-game box art kept
    rendering for the 2013 novel after the JSON was corrected.

    Backward-compat: a cached file with no sidecar is treated as fresh
    (the legacy fleet doesn't have sidecars yet). Once any cache run
    overwrites a file, the sidecar lands and future URL changes are
    detected.
    """
    if is_already_local(url):
        # Idempotency: if JSON already points local, no work needed.
        return None

    if not SLUG_RE.match(slug):
        # Defense-in-depth: never let a malformed slug (e.g. "../secrets")
        # escape the cache directory when building the output path.
        print(f"  ⚠ skipping unsafe slug: {slug!r}", file=sys.stderr)
        return None

    out_dir.mkdir(parents=True, exist_ok=True)
    sidecar = out_dir / f"{slug}.url"

    # Skip if a recent local file already exists for this slug AND a
    # sidecar confirms it came from the same upstream URL. We only reach
    # this branch when the JSON points to an *upstream* URL — i.e., a
    # new or manually re-pointed record. Legacy records whose JSON
    # points to /tsundoku/cached/<slug> short-circuit at the top of
    # cache_one (is_already_local), so they never touch this sidecar
    # logic and are not invalidated by it.
    for existing in sorted(out_dir.glob(f"{slug}.*")):
        if existing.suffix == ".url":
            continue
        age_days = (time.time() - existing.stat().st_mtime) / 86400
        if age_days >= SKIP_IF_NEWER_THAN_DAYS:
            break
        if not sidecar.exists() or sidecar.read_text().strip() != url:
            # Either the cached bytes came from a different URL, or we
            # have no record of where they came from. Treat as stale.
            existing.unlink()
            break
        ext = existing.suffix.lstrip(".")
        return f"{ASTRO_BASE}cached/{out_dir.name}/{slug}.{ext}", ext

    result = download(url)
    if rate_limit_s:
        time.sleep(rate_limit_s)
    if result is None:
        return None

    data, ext = result
    target = out_dir / f"{slug}.{ext}"
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(target)
    sidecar.write_text(url)
    return f"{ASTRO_BASE}cached/{out_dir.name}/{slug}.{ext}", ext


def _resolve_local_path(local_url: str, out_dir: Path) -> Path | None:
    """Map a /tsundoku/cached/<dir>/<slug>.<ext> URL to its local Path."""
    if not local_url:
        return None
    name = local_url.rsplit("/", 1)[-1]
    return out_dir / name


def process_authors(limit: int, dry_run: bool, rate_limit_s: float) -> dict:
    """Walk every author file, download photo if needed, rewrite JSON.

    `limit` counts *new downloads*, not records seen.

    "Already cached" requires both (a) photo_url points at /cached/ AND
    (b) the file actually exists on disk. The CI cache restore can be
    incomplete (the saved cache plateaued at ~40% of files), so the
    URL-only heuristic was reporting "cached" while leaving 404s for
    Pages to serve. When the file is missing, we fall back to the
    upstream `photo_url_source` for re-download.
    """
    out_dir = PUBLIC_CACHED / "authors"
    counts = {"total": 0, "cached_already": 0, "downloaded": 0, "failed": 0, "skipped": 0, "failed_by_status": {}}

    for path in sorted(AUTHORS_DIR.glob("*.json")):
        if limit and counts["downloaded"] >= limit:
            break
        doc = json.loads(path.read_text(encoding="utf-8"))
        url = doc.get("photo_url")
        if not url:
            continue
        counts["total"] += 1
        slug = doc.get("slug") or path.stem

        if slug in KNOWN_UNFETCHABLE_AUTHOR_SLUGS:
            counts["skipped"] += 1
            continue

        if is_already_local(url):
            local_path = _resolve_local_path(url, out_dir)
            if local_path and local_path.exists():
                counts["cached_already"] += 1
                continue
            # Cache miss: file is gone but JSON insists it's local.
            # Recover via the upstream attribution URL.
            recovery_url = doc.get("photo_url_source")
            if not recovery_url:
                counts["skipped"] += 1
                continue
            url = recovery_url

        if dry_run:
            print(f"  WOULD CACHE {slug}: {url[:80]}")
            counts["downloaded"] += 1
            continue

        result = cache_one(url=url, out_dir=out_dir, slug=slug, rate_limit_s=rate_limit_s)
        if result is None:
            counts["failed"] += 1
            status_key = str(_last_fail_status) if _last_fail_status else "network-error"
            counts["failed_by_status"][status_key] = counts["failed_by_status"].get(status_key, 0) + 1
            print(f"  FAIL {slug}: [{status_key}] {url[:80]}")
            continue

        local_url, _ext = result
        # Preserve upstream attribution when first caching this record.
        if not doc.get("photo_url_source"):
            doc["photo_url_source"] = url
        doc["photo_url"] = local_url
        doc["photo_cached_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        save_json(path, doc)
        counts["downloaded"] += 1
        print(f"  ✓ {slug} → {local_url}")

    return counts


def process_books(limit: int, dry_run: bool, rate_limit_s: float) -> dict:
    """Walk every book file, download cover if needed, rewrite JSON.

    cover_url and cover_url_large can both exist; cover_url_large is preferred
    when present. We cache only one (the larger), and rewrite both fields to
    point to the same local URL — saving disk and bandwidth.
    """
    out_dir = PUBLIC_CACHED / "covers"
    counts = {"total": 0, "cached_already": 0, "downloaded": 0, "failed": 0, "skipped": 0, "failed_by_status": {}}

    for path in sorted(BOOKS_DIR.glob("*.json")):
        if limit and counts["downloaded"] >= limit:
            break
        doc = json.loads(path.read_text(encoding="utf-8"))
        # Prefer the largest-resolution upstream URL.
        url = doc.get("cover_url_large") or doc.get("cover_url")
        if not url:
            continue
        counts["total"] += 1

        if is_already_local(url):
            local_path = _resolve_local_path(url, out_dir)
            if local_path and local_path.exists():
                counts["cached_already"] += 1
                continue
            # Cache restore was incomplete; fall back to upstream source
            # captured the first time we cached. See process_authors().
            recovery_url = doc.get("cover_url_large_source") or doc.get("cover_url_source")
            if not recovery_url:
                counts["skipped"] += 1
                continue
            url = recovery_url

        slug = doc.get("slug") or path.stem

        if dry_run:
            print(f"  WOULD CACHE {slug}: {url[:80]}")
            counts["downloaded"] += 1
            continue

        result = cache_one(url=url, out_dir=out_dir, slug=slug, rate_limit_s=rate_limit_s)
        if result is None:
            counts["failed"] += 1
            status_key = str(_last_fail_status) if _last_fail_status else "network-error"
            counts["failed_by_status"][status_key] = counts["failed_by_status"].get(status_key, 0) + 1
            print(f"  FAIL {slug}: [{status_key}] {url[:80]}")
            continue

        local_url, _ext = result
        if doc.get("cover_url") and not doc.get("cover_url_source") and not is_already_local(doc["cover_url"]):
            doc["cover_url_source"] = doc["cover_url"]
        if doc.get("cover_url_large") and not doc.get("cover_url_large_source") and not is_already_local(doc["cover_url_large"]):
            doc["cover_url_large_source"] = doc["cover_url_large"]
        # Both small and large now point to the same local file — Astro serves it once.
        if "cover_url" in doc:
            doc["cover_url"] = local_url
        if "cover_url_large" in doc:
            doc["cover_url_large"] = local_url
        doc["cover_cached_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        save_json(path, doc)
        counts["downloaded"] += 1
        print(f"  ✓ {slug} → {local_url}")

    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Cache photos / covers locally")
    parser.add_argument("--target", choices=("authors", "books", "all"), default="all")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--rate-limit",
        type=float,
        default=0.2,
        help="Seconds between downloads to be a good citizen of upstream CDNs (default 0.2)",
    )
    args = parser.parse_args()

    if not args.dry_run:
        PUBLIC_CACHED.mkdir(parents=True, exist_ok=True)

    summary = {}
    if args.target in ("authors", "all"):
        print("Caching author photos...")
        summary["authors"] = process_authors(args.limit, args.dry_run, args.rate_limit)
    if args.target in ("books", "all"):
        print("\nCaching book covers...")
        summary["books"] = process_books(args.limit, args.dry_run, args.rate_limit)

    print("\n=== Summary ===")
    for kind, c in summary.items():
        print(
            f"  {kind:8s}  total={c['total']:5d}  "
            f"already-cached={c['cached_already']:5d}  "
            f"downloaded={c['downloaded']:5d}  "
            f"failed={c['failed']:4d}  "
            f"skipped={c['skipped']:4d}"
        )
        # Failure-reason breakdown — added after #234: the previous summary
        # gave a bare "failed" count with no way to tell "transiently
        # rate-limited, will likely succeed on the next run" apart from
        # "permanently invalid URL, will NEVER succeed no matter how many
        # runs happen" (e.g. HTTP 400 from Wikimedia's now-rejected
        # path-based thumbnail URLs — see download()'s docstring). Sorted
        # by count descending so the dominant failure mode is first.
        by_status = c.get("failed_by_status") or {}
        for status_key, n in sorted(by_status.items(), key=lambda kv: -kv[1]):
            label = "network error (no HTTP response)" if status_key == "network-error" else f"HTTP {status_key}"
            print(f"    - {label}: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
