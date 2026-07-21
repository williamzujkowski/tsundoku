"""Build-time guard against emitting a /cached/ image URL whose file
doesn't actually exist on disk.

## The bug this fixes (production 404, e.g. /authors/william-shakespeare/)

`scripts/cache-photos.py` downloads book covers / author photos into the
gitignored `public/cached/` directory and rewrites the record's
`cover_url` / `photo_url` field to a local `/tsundoku/cached/...` path
once the download succeeds. That JSON rewrite is what gets committed —
the binary file itself never is (gitignored, and CI's actions/cache for
`public/cached/` is a *separate*, independently-converging store, keyed
per-run, restored from the most recent prior run).

Two ways this can desync (a record's JSON says "local" while the actual
file is absent from a given build's `public/cached/`):

  1. The JSON was updated during a local/interactive session (the binary
     only ever existed on that machine, gitignored, never entered any CI
     run's persisted actions-cache).
  2. CI's own photo cache hasn't converged yet for this record — it's
     chunked (`--limit`) and Wikimedia in particular has an extremely low
     success rate from the Actions runner IP (see the deploy-run
     investigation referenced in the PR that added this guard), so a
     freshly-added or not-yet-recovered record can sit "JSON says local,
     file missing" across many runs.

`cache-photos.py` (`process_authors`/`process_books`) already recovers
from this *when it can*: it checks the file actually exists before
trusting a "local" URL, and re-downloads from the preserved
`*_source` field if not. But when that re-download *also* fails (as it
overwhelmingly does for Wikimedia right now), the JSON is left exactly as
committed — still claiming a local path the build will never have. The
generators that emit into `public/browse-data.json` / `public/search-index.json`
(this module's Python consumers) and the `.astro` page templates (the
mirrored `src/utils/imageGuard.ts`) are the LAST point before that URL
reaches a `<img src>` — so this is where the guarantee has to be
absolute: never emit a `/cached/` URL unless the file is actually there
*right now*, in *this* build.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PUBLIC_DIR = REPO_ROOT / "public"
ASTRO_BASE = "/tsundoku/"


def resolve_image_url(
    url: str | None,
    source_url: str | None = None,
    *,
    public_dir: Path = PUBLIC_DIR,
) -> str | None:
    """Return a URL that is safe to render right now, or None.

    - Falsy `url` -> None (caller renders its placeholder).
    - `url` is not a local `/cached/` path (empty check aside, this covers
      plain remote http(s) URLs) -> returned unchanged; nothing to verify.
    - `url` IS a local `/cached/` path and the file exists on disk in
      `public_dir` -> returned unchanged.
    - `url` IS a local `/cached/` path but the file is MISSING -> falls
      back to `source_url` (the original upstream URL, preserved by
      cache-photos.py in `cover_url_source` / `cover_url_large_source` /
      `photo_url_source`), or None if there's no source on record either.

    `public_dir` is overridable for tests; production callers always use
    the default (the real `public/` directory this repo builds from).
    """
    if not url:
        return None
    if not (url.startswith(f"{ASTRO_BASE}cached/") or url.startswith("/cached/")):
        return url
    # Both "/tsundoku/cached/covers/x.jpg" and "/cached/covers/x.jpg" carry
    # the same suffix after the LAST "cached/" — split on that literal
    # rather than assuming which base prefix is present.
    relative = url.rsplit("cached/", 1)[1]
    if (public_dir / "cached" / relative).exists():
        return url
    return source_url or None
