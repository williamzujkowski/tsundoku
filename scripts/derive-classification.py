#!/usr/bin/env python3
"""Derive a coarse DDC/LCC baseline for books missing both classifications.

For ~280 books in the residual gap, neither Open Library nor Wikidata
carries a DDC or LCC. They're the obscure tail — pre-1970, non-Western,
academic/specialist titles. The virtual shelf and DDC stacks features
need *something* on these, otherwise they vanish from those views.

This script reverses the existing `recategorize.py::category_from_*`
mapping: for each missing-both record, look at the curated `category`
field and assign a single shelf-level DDC + LCC class. Tagged with
provenance `derived_v1` (rank 5 in SOURCE_RANK) so any future
authoritative classification — manual, ol_classification_v2,
wikidata_v1 — overwrites it via fields_overwritable.

The mapping is intentionally coarse: we pick the parent class, not a
specific call number. A literature record gets DDC 800 + LCC P, not
the precise 813.54 + PS3553.A654.

Usage:
  python scripts/derive-classification.py             # dry-run
  python scripts/derive-classification.py --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from enrichment_config import BOOKS_DIR
from json_merge import provenance_merge, save_json


# Category → (DDC class, LCC class). The class is the broad shelf area.
# Multiple keys can map to the same class — kept verbose for readability.
CATEGORY_TO_CLASS: dict[str, tuple[str, str]] = {
    "Literature":              ("800", "P"),    # general literature
    "Poetry":                  ("808.81", "PN"),  # poetry general
    "Drama":                   ("808.82", "PN"),  # drama general
    "Literary Criticism":      ("809", "PN"),   # literary history & crit
    "Classics":                ("880", "PA"),   # Greek + Latin classics
    "Non-Western Literature":  ("895", "PL"),   # East Asian + south-asian
    "Science Fiction":         ("808.83876", "PN3433"),  # SF as genre
    "Fantasy":                 ("808.83766", "PN3435"),  # fantasy genre
    "Mystery":                 ("808.83872", "PN3448"),  # detective fiction
    "Horror":                  ("808.8387", "PN3435"),   # horror genre
    "Philosophy":              ("100", "B"),
    "Non-Western Philosophy":  ("181", "B"),    # Eastern philosophy
    "Religion":                ("200", "BL"),
    "Political Theory":        ("320", "JA"),
    "Economics":               ("330", "HB"),
    "Mathematics":             ("510", "QA"),
    "Science":                 ("500", "Q"),
    "Computer Science":        ("005", "QA76"),
    "Security":                ("005.8", "QA76.9"),  # computer security
    "Complex Systems":         ("003", "Q295"),  # general systems / cybernetics
    "History":                 ("900", "D"),
    "Global History":          ("909", "D"),
    "Non-Western History":     ("950", "DS"),     # Asian / Middle Eastern history
    "Biography/Memoir":        ("920", "CT"),
    "Essays":                  ("814", "PN6014"),  # essays as a literary form
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Derive coarse DDC/LCC for missing-both records from category"
    )
    parser.add_argument("--apply", action="store_true", help="Write changes")
    parser.add_argument("--limit", type=int, default=0, help="Process at most N records")
    args = parser.parse_args()

    candidates: list[tuple[Path, dict, dict]] = []  # (path, doc, fields_to_add)
    unmapped: dict[str, int] = {}

    for f in sorted(BOOKS_DIR.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        has_ddc = bool(d.get("ddc"))
        has_lcc = bool(d.get("lcc"))
        if has_ddc and has_lcc:
            continue
        cat = d.get("category", "")
        mapping = CATEGORY_TO_CLASS.get(cat)
        if not mapping:
            unmapped[cat] = unmapped.get(cat, 0) + 1
            continue
        ddc, lcc = mapping
        new_fields: dict = {}
        if not has_ddc:
            new_fields["ddc"] = [ddc]
        if not has_lcc:
            new_fields["lcc"] = [lcc]
        if new_fields:
            candidates.append((f, d, new_fields))

    if args.limit:
        candidates = candidates[: args.limit]

    print(f"Records to derive: {len(candidates)}")
    if unmapped:
        print(f"Unmapped categories: {sum(unmapped.values())} records across "
              f"{len(unmapped)} categories: {sorted(unmapped.items(), key=lambda kv: -kv[1])}")

    n_written = 0
    by_field: dict[str, int] = {"ddc": 0, "lcc": 0}
    for f, d, new_fields in candidates:
        for k in new_fields:
            by_field[k] = by_field.get(k, 0) + 1
        changed, _ = provenance_merge(d, new_fields, source="derived_v1")
        if changed:
            n_written += 1
            if args.apply:
                save_json(f, d)

    verb = "wrote" if args.apply else "would write"
    print(f"\n{verb} {n_written} records: +{by_field['ddc']} DDC, +{by_field['lcc']} LCC")
    if not args.apply:
        print("Dry-run — pass --apply to commit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
