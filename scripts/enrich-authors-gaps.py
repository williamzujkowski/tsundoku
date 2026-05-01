#!/usr/bin/env python3
"""Fill missing bio / photo / etc. on existing author records using multi-source fallback.

Unlike enrich-authors.py (which generates new author files), this script
walks existing src/content/authors/*.json records that are missing fields
and tries each source in order, additive-merging in only the empty fields.

Sources tried, in order:
  1. Open Library author page (richer than search.json — includes bio, photos array)
  2. Wikidata (description + P18 image — last-mile fallback)

Wikipedia (already used by enrich-authors.py) is skipped here because the
records being filled are the ones where Wikipedia *already failed* — usually
disambiguation pages, multi-author entries, or cataloging-artifact names.

For each "stuck" name, we also try cleaned variants:
  - "Robert Jordan & Brandon Sanderson" → also try "Robert Jordan"
  - "Petr Alekseevich Kropotkin (kni︠a︡zʹ)" → also try "Petr Alekseevich Kropotkin"

Usage:
  python scripts/enrich-authors-gaps.py                # dry-run report
  python scripts/enrich-authors-gaps.py --apply        # write changes
  python scripts/enrich-authors-gaps.py --apply --limit 50

Goes through the http_cache layer (#91), so re-runs within the source TTL
don't hammer Open Library or Wikidata. Uses additive_merge (#90) — never
overwrites a non-empty field.
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from author_sources import (
    _olid_from_url,
    candidate_names,
    from_open_library_author_page,
    from_wikidata,
)
from enrichment_config import AUTHORS_DIR
from json_merge import additive_merge, save_json


GAP_FIELDS = ("bio", "photo_url")  # what counts as a "gap" worth filling
RATE_LIMIT_S = 0.5  # be polite to OL + Wikidata


def has_any_gap(doc: dict) -> bool:
    return any(not doc.get(f) for f in GAP_FIELDS)


def try_sources_for(doc: dict) -> dict:
    """Walk sources in order, returning aggregated fields to add (additive)."""
    name = doc.get("name", "")
    olid = _olid_from_url(doc.get("open_library_url", ""))

    aggregated: dict = {}

    # Source 1 — Open Library author page (use cached OLID if we have one)
    new = from_open_library_author_page(olid=olid, name=name if not olid else None)
    if new:
        for k, v in new.items():
            aggregated.setdefault(k, v)

    # Source 2 — Wikidata, with name-variant fallback
    if any(f not in aggregated and not doc.get(f) for f in GAP_FIELDS):
        for variant in candidate_names(name):
            new = from_wikidata(name=variant)
            if new:
                for k, v in new.items():
                    aggregated.setdefault(k, v)
                break  # took whatever the first matching variant gave us

    return aggregated


def main() -> int:
    parser = argparse.ArgumentParser(description="Fill author bio/photo gaps via multi-source fallback")
    parser.add_argument("--apply", action="store_true", help="Actually write changes; default is dry-run")
    parser.add_argument("--limit", type=int, default=0, help="Process at most N gap records")
    args = parser.parse_args()

    files = sorted(AUTHORS_DIR.glob("*.json"))
    candidates = []
    for p in files:
        doc = json.loads(p.read_text(encoding="utf-8"))
        if has_any_gap(doc):
            candidates.append((p, doc))

    print(f"Authors with gaps: {len(candidates)} of {len(files)}")
    if args.limit:
        candidates = candidates[: args.limit]
        print(f"Processing first {len(candidates)} (--limit)")

    n_filled = 0
    n_unchanged = 0
    n_changed_files: list[Path] = []

    for i, (path, doc) in enumerate(candidates, 1):
        print(f"[{i}/{len(candidates)}] {doc.get('name', path.stem)}")
        before_keys = set(k for k, v in doc.items() if v not in (None, "", []))

        proposed = try_sources_for(doc)
        time.sleep(RATE_LIMIT_S)

        if not proposed:
            n_unchanged += 1
            print("  no source returned anything")
            continue

        # Additive merge — never overwrite, only fill missing.
        changed = additive_merge(doc, proposed)
        if changed:
            n_filled += 1
            new_keys = set(k for k, v in doc.items() if v not in (None, "", []))
            added = sorted(new_keys - before_keys)
            print(f"  {'WOULD ADD' if not args.apply else 'added'}: {', '.join(added)}")
            if args.apply:
                save_json(path, doc)
                n_changed_files.append(path)
        else:
            n_unchanged += 1

    print(f"\nDone:")
    print(f"  filled:    {n_filled}{' (written)' if args.apply else ' (would write)'}")
    print(f"  unchanged: {n_unchanged}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
