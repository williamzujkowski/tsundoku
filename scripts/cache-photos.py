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
with the runtime broken-image fallback in Layout.astro, the site is
"belt + suspenders" resilient to upstream rot.

Usage:
  python scripts/cache-photos.py                   # download all
  python scripts/cache-photos.py --target authors  # only authors
  python scripts/cache-photos.py --target books    # only books
  python scripts/cache-photos.py --limit 50        # sample
  python scripts/cache-photos.py --dry-run         # plan only, no writes

CI integration: this script runs in the prebuild step between content
sync and astro build. The public/cached/ directory is gitignored —
actions/cache@v4 persists it across CI runs.
"""

import argparse
import json
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


def download(url: str) -> tuple[bytes, str] | None:
    """Fetch image bytes + extension, or None on failure.

    Goes through fetch_with_retry so 429/503 from Wikimedia and other
    rate-limiting CDNs auto-back-off and retry rather than dropping the
    record. Per a prior session, ~24% of cache-photos downloads were
    lost to silently-swallowed 429s.
    """
    body, status, headers = fetch_with_retry(url, timeout=DOWNLOAD_TIMEOUT)
    if body is None:
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
    """Download `url` into `out_dir/{slug}.{ext}`. Returns (local_url, ext) or None."""
    if is_already_local(url):
        # Idempotency: if JSON already points local, no work needed.
        return None

    out_dir.mkdir(parents=True, exist_ok=True)

    # Skip if a recent local file already exists for this slug.
    for existing in out_dir.glob(f"{slug}.*"):
        age_days = (time.time() - existing.stat().st_mtime) / 86400
        if age_days < SKIP_IF_NEWER_THAN_DAYS:
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
    return f"{ASTRO_BASE}cached/{out_dir.name}/{slug}.{ext}", ext


def process_authors(limit: int, dry_run: bool, rate_limit_s: float) -> dict:
    """Walk every author file, download photo if needed, rewrite JSON."""
    out_dir = PUBLIC_CACHED / "authors"
    counts = {"total": 0, "cached_already": 0, "downloaded": 0, "failed": 0, "skipped": 0}

    for path in sorted(AUTHORS_DIR.glob("*.json")):
        if limit and counts["total"] >= limit:
            break
        doc = json.loads(path.read_text(encoding="utf-8"))
        url = doc.get("photo_url")
        if not url:
            continue
        counts["total"] += 1

        if is_already_local(url):
            counts["cached_already"] += 1
            continue

        slug = doc.get("slug") or path.stem

        if dry_run:
            print(f"  WOULD CACHE {slug}: {url[:80]}")
            counts["downloaded"] += 1
            continue

        result = cache_one(url=url, out_dir=out_dir, slug=slug, rate_limit_s=rate_limit_s)
        if result is None:
            counts["failed"] += 1
            print(f"  FAIL {slug}: {url[:80]}")
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
    counts = {"total": 0, "cached_already": 0, "downloaded": 0, "failed": 0, "skipped": 0}

    for path in sorted(BOOKS_DIR.glob("*.json")):
        if limit and counts["total"] >= limit:
            break
        doc = json.loads(path.read_text(encoding="utf-8"))
        # Prefer the largest-resolution upstream URL.
        url = doc.get("cover_url_large") or doc.get("cover_url")
        if not url:
            continue
        counts["total"] += 1

        if is_already_local(url):
            counts["cached_already"] += 1
            continue

        slug = doc.get("slug") or path.stem

        if dry_run:
            print(f"  WOULD CACHE {slug}: {url[:80]}")
            counts["downloaded"] += 1
            continue

        result = cache_one(url=url, out_dir=out_dir, slug=slug, rate_limit_s=rate_limit_s)
        if result is None:
            counts["failed"] += 1
            print(f"  FAIL {slug}: {url[:80]}")
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
            f"failed={c['failed']:4d}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
