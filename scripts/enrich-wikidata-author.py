#!/usr/bin/env python3
"""Wikidata-driven enrichment for authors — Phase B item 5 of epic #124.

For every author with an `open_library_url` (or `ol_author_key`), resolves
the matching Wikidata QID via P648, then fetches the entity and pulls:

  • nationality          — ISO 3166-1 alpha-2 codes (P27)
  • alternate_names      — pen names + transliterations (P742)
  • movements            — literary movements (P135, label-resolved)
  • awards               — major awards with year (P166 + P585)
  • viaf_id              — VIAF cross-reference (P214)
  • ol_author_key        — cross-validation (P648)

Provenance source `wikidata_v1` (rank 85). All fields above fill-only
(never overwrite) since Wikipedia/OL bios already populate the basics
elsewhere — this is purely additive.

Usage:
  python scripts/enrich-wikidata-author.py             # dry-run report
  python scripts/enrich-wikidata-author.py --apply     # write changes
  python scripts/enrich-wikidata-author.py --apply --slug george-orwell
  python scripts/enrich-wikidata-author.py --apply --limit 200
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from json_merge import provenance_merge, save_json
from wikidata import (
    qids_by_ol_author_keys,
    fetch_entity,
    fields_for_author,
    resolve_qid_labels,
)


SOURCE = "wikidata_v1"
RATE_LIMIT_S = 0.5

AUTHORS_DIR = Path(__file__).parent.parent / "src" / "content" / "authors"

# All author fields are fill-only (no overwrite) — the existing bio + photo
# from OL/Wikipedia is canonical for those, and we don't write to them.
FIELDS_OVERWRITABLE: frozenset[str] = frozenset()

# Extract the OL author key from open_library_url like
# "https://openlibrary.org/authors/OL118077A" or "/authors/OL118077A".
_OL_AUTHOR_PATTERN = re.compile(r"/authors/(OL\d+A)")


def ol_author_key(author: dict) -> str | None:
    if author.get("ol_author_key"):
        return author["ol_author_key"]
    url = author.get("open_library_url") or ""
    m = _OL_AUTHOR_PATTERN.search(url)
    return f"/authors/{m.group(1)}" if m else None


def collect_authors() -> list[tuple[Path, dict, str]]:
    """Authors with an extractable OL author key."""
    out = []
    for f in sorted(AUTHORS_DIR.glob("*.json")):
        a = json.loads(f.read_text(encoding="utf-8"))
        key = ol_author_key(a)
        if key:
            out.append((f, a, key))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Wikidata author enrichment")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--slug", help="Process only this slug")
    parser.add_argument("--report-overwrites", action="store_true")
    args = parser.parse_args()

    all_authors = collect_authors()
    if args.slug:
        all_authors = [(p, a, k) for p, a, k in all_authors if a.get("slug") == args.slug]

    keys = list({k for _, _, k in all_authors})
    print(f"Resolving QIDs for {len(keys)} OL author keys...")
    qids = qids_by_ol_author_keys(keys)
    print(f"  Found Wikidata QIDs for {len(qids)} of {len(keys)} ({100*len(qids)/max(len(keys),1):.0f}%)")

    candidates = [(p, a, qids[k]) for p, a, k in all_authors if k in qids]
    if args.limit:
        candidates = candidates[: args.limit]

    print(f"Fetching Wikidata entities for {len(candidates)} authors...")

    raw_list: list[tuple[Path, dict, dict]] = []
    label_qids: set[str] = set()

    for i, (path, author, qid) in enumerate(candidates, 1):
        entity = fetch_entity(qid)
        time.sleep(RATE_LIMIT_S)
        if not entity:
            continue
        fields = fields_for_author(qid, entity)
        for mq in fields.get("_movement_qids") or []:
            label_qids.add(mq)
        for a in fields.get("_awards") or []:
            if a.get("_qid"):
                label_qids.add(a["_qid"])
        raw_list.append((path, author, fields))
        if i % 100 == 0:
            print(f"  [{i}/{len(candidates)}]  collected {len(raw_list)} entities")

    print(f"\nResolving {len(label_qids)} movement/award labels...")
    label_lookup = resolve_qid_labels(label_qids) if label_qids else {}
    print(f"  Resolved {len(label_lookup)}/{len(label_qids)} labels")

    n_filled = 0
    counters: dict[str, int] = {}

    for path, author, raw in raw_list:
        fields = dict(raw)

        # Resolve movement labels
        movements = []
        for mq in fields.pop("_movement_qids", None) or []:
            label = label_lookup.get(mq)
            if label and label not in movements:
                movements.append(label)
        if movements:
            fields["movements"] = movements

        # Resolve award labels
        awards = []
        for a in fields.pop("_awards", None) or []:
            qid = a.get("_qid")
            if not qid:
                continue
            label = label_lookup.get(qid)
            if not label:
                continue
            entry: dict = {"name": label}
            if "year" in a:
                entry["year"] = a["year"]
            awards.append(entry)
        if awards:
            fields["awards"] = awards

        if not fields:
            continue

        for k in fields:
            counters[k] = counters.get(k, 0) + 1

        if args.apply:
            changed, audit = provenance_merge(
                author, fields, source=SOURCE, fields_overwritable=FIELDS_OVERWRITABLE,
            )
            if changed:
                save_json(path, author)
                n_filled += 1

    print(f"\nDone. {n_filled} authors got new fields.")
    print("\nField fill counts:")
    for k in sorted(counters):
        if k.startswith("_"):
            continue
        print(f"  +{k:30s}  {counters[k]}")

    if not args.apply:
        print("\nDry-run — pass --apply to write")

    return 0


if __name__ == "__main__":
    sys.exit(main())
