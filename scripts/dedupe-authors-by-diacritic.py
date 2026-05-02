#!/usr/bin/env python3
"""Merge author records that differ only in diacritics.

Audit found 5 near-duplicate author pairs (Émile Zola / Emile Zola,
Charlotte Brontë / Charlotte Bronte, etc.) where books were split
across two records. The diacritic form is the canonical proper name;
this script:

  1. Updates every book that references the non-canonical variant to
     reference the canonical one.
  2. Merges any unique fields from the non-canonical author record
     into the canonical one (additive — never overwrites).
  3. Deletes the non-canonical author file.

Usage:
  python scripts/dedupe-authors-by-diacritic.py             # dry-run
  python scripts/dedupe-authors-by-diacritic.py --apply     # write
"""

import argparse
import json
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from json_merge import additive_merge, save_json

BOOKS_DIR = Path(__file__).parent.parent / "src" / "content" / "books"
AUTHORS_DIR = Path(__file__).parent.parent / "src" / "content" / "authors"


def fold(s: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c)).lower().strip()


def has_diacritics(s: str) -> bool:
    return any(unicodedata.combining(c) for c in unicodedata.normalize('NFKD', s))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    # Find author records grouped by diacritic-folded name
    authors = []
    for f in sorted(AUTHORS_DIR.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        authors.append((f, d))

    groups = defaultdict(list)
    for f, d in authors:
        groups[fold(d["name"])].append((f, d))

    near_dupes = {k: v for k, v in groups.items() if len(v) > 1}
    print(f"Found {len(near_dupes)} near-duplicate author groups")

    if not near_dupes:
        return 0

    # Resolve each group: pick canonical (diacritic-bearing variant)
    plans = []
    for key, records in near_dupes.items():
        # Sort: diacritic-bearing first, then alphabetical
        records.sort(key=lambda fd: (0 if has_diacritics(fd[1]["name"]) else 1, fd[1]["name"]))
        canonical_f, canonical = records[0]
        non_canonicals = records[1:]
        plans.append({
            "canonical_file": canonical_f,
            "canonical_name": canonical["name"],
            "canonical_data": canonical,
            "non_canonical": [(f, d["name"], d) for f, d in non_canonicals],
        })

    print()
    for p in plans:
        print(f"  Canonical: {p['canonical_name']}")
        for nf, nn, _ in p["non_canonical"]:
            print(f"    Will merge in: {nn}")

    # Update books and merge records
    book_updates = 0
    for p in plans:
        non_canonical_names = {nn for _, nn, _ in p["non_canonical"]}
        for bf in sorted(BOOKS_DIR.glob("*.json")):
            d = json.loads(bf.read_text(encoding="utf-8"))
            if d.get("author") in non_canonical_names:
                if args.apply:
                    d["author"] = p["canonical_name"]
                    save_json(bf, d)
                book_updates += 1

        # Merge non-canonical author fields into canonical (additive only)
        merged = dict(p["canonical_data"])
        for _, _, nc_data in p["non_canonical"]:
            additive_merge(merged, nc_data)
        # Always keep the canonical name
        merged["name"] = p["canonical_name"]
        # Refresh book_count later via a separate script if needed; for
        # now sum the values we have on the records (they were per-record)
        merged["book_count"] = sum((d.get("book_count") or 0) for _, _, d in p["non_canonical"]) + (p["canonical_data"].get("book_count") or 0)

        if args.apply:
            save_json(p["canonical_file"], merged)
            for nf, _, _ in p["non_canonical"]:
                nf.unlink()

    print(f"\nDone. {book_updates} book records updated, {sum(len(p['non_canonical']) for p in plans)} duplicate author files removed.")
    if not args.apply:
        print("Dry-run — pass --apply to write")

    return 0


if __name__ == "__main__":
    sys.exit(main())
