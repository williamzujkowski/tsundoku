#!/usr/bin/env python3
"""Wikidata-driven enrichment for books — Phase B of epic #124.

For every book with an `ol_work_key`, resolves the matching Wikidata QID
via P648 (Open Library work ID) in batched SPARQL queries, then fetches
the entity and pulls structured first-edition + awards + series data.

The provenance_merge uses source `wikidata_v1` (rank 85). It is allowed to
overwrite legacy data, ol_classification_v2 (60), and ol_firstedition_v1
(80) on these fields:

  • first_published             — Wikidata's P577 is more reliable for
                                  ancient and famous books than OL editions
                                  consensus.
  • first_published_circa
  • original_title              — fills empties (won't overwrite OL's pick)
  • original_language

Other fields are filled only when empty.

Usage:
  python scripts/enrich-wikidata-book.py             # dry-run report
  python scripts/enrich-wikidata-book.py --apply     # write changes
  python scripts/enrich-wikidata-book.py --apply --limit 100
  python scripts/enrich-wikidata-book.py --apply --slug 1984
  python scripts/enrich-wikidata-book.py --resolve-qids-only --apply
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from enrichment_config import BOOKS_DIR
from json_merge import provenance_merge, save_json
from wikidata import (
    qids_by_ol_work_keys,
    fetch_entity,
    fields_for_book,
    resolve_qid_labels,
)


SOURCE = "wikidata_v1"
RATE_LIMIT_S = 0.5

# Wikidata's P577 is more authoritative than OL's editions consensus for
# the work-level publication year — especially for ancient and famous works
# where OL's edition records start mid-18th century.
FIELDS_OVERWRITABLE = frozenset({
    "first_published",
    "first_published_circa",
})


def collect_books() -> list[tuple[Path, dict]]:
    out = []
    for f in sorted(BOOKS_DIR.glob("*.json")):
        b = json.loads(f.read_text(encoding="utf-8"))
        out.append((f, b))
    return out


def resolve_all_qids(books: list[tuple[Path, dict]]) -> dict[str, str]:
    """Build the OL work key → QID map in one batched SPARQL pass."""
    keys = [b.get("ol_work_key") for _, b in books if b.get("ol_work_key")]
    keys = list(set(keys))
    print(f"Resolving QIDs for {len(keys)} OL work keys via SPARQL...")
    qids = qids_by_ol_work_keys(keys)
    print(f"  Found Wikidata QIDs for {len(qids)} of {len(keys)} ({100*len(qids)/max(len(keys),1):.0f}%)")
    return qids


def derive_publisher_label(fields: dict, label_lookup: dict[str, str]) -> dict:
    """Replace _publisher_qid with original_publisher (resolved label)."""
    pub_qid = fields.pop("_publisher_qid", None)
    if pub_qid:
        label = label_lookup.get(pub_qid)
        if label:
            fields["original_publisher"] = label
    return fields


def derive_awards(fields: dict, label_lookup: dict[str, str]) -> dict:
    """Replace _awards with awards (resolved labels)."""
    raw = fields.pop("_awards", None)
    if not raw:
        return fields
    awards = []
    for a in raw:
        qid = a.get("_qid")
        if not qid:
            continue
        name = label_lookup.get(qid)
        if not name:
            continue
        entry: dict = {"name": name}
        if "year" in a:
            entry["year"] = a["year"]
        awards.append(entry)
    if awards:
        fields["awards"] = awards
    return fields


def derive_series(fields: dict, label_lookup: dict[str, str]) -> dict:
    raw = fields.pop("_series", None)
    if not raw:
        return fields
    qid = raw.get("_qid")
    if not qid:
        return fields
    name = label_lookup.get(qid)
    if not name:
        return fields
    entry: dict = {"name": name}
    if "position" in raw:
        entry["position"] = raw["position"]
    fields["series"] = entry
    return fields


def main() -> int:
    parser = argparse.ArgumentParser(description="Wikidata book enrichment")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--slug", help="Process only this slug")
    parser.add_argument("--resolve-qids-only", action="store_true",
                        help="Just batch-resolve QIDs, don't fetch entities")
    parser.add_argument("--report-overwrites", action="store_true")
    args = parser.parse_args()

    all_books = collect_books()
    if args.slug:
        all_books = [(p, b) for p, b in all_books if b.get("slug") == args.slug]

    qids = resolve_all_qids(all_books)
    if args.resolve_qids_only:
        return 0

    candidates = [(p, b, qids[b["ol_work_key"]])
                  for p, b in all_books
                  if b.get("ol_work_key") in qids]

    if args.limit:
        candidates = candidates[: args.limit]

    print(f"Fetching Wikidata entities for {len(candidates)} books...")

    # Pass 1: fetch entities, extract raw fields with embedded _publisher_qid /
    # _awards / _series QIDs so we can batch-resolve labels.
    raw_fields_list: list[tuple[Path, dict, dict]] = []
    label_qids: set[str] = set()

    for i, (path, book, qid) in enumerate(candidates, 1):
        entity = fetch_entity(qid)
        time.sleep(RATE_LIMIT_S)
        if not entity:
            continue
        fields = fields_for_book(qid, entity)
        if "_publisher_qid" in fields:
            label_qids.add(fields["_publisher_qid"])
        for a in fields.get("_awards") or []:
            if a.get("_qid"):
                label_qids.add(a["_qid"])
        if (fields.get("_series") or {}).get("_qid"):
            label_qids.add(fields["_series"]["_qid"])
        raw_fields_list.append((path, book, fields))
        if i % 100 == 0:
            print(f"  [{i}/{len(candidates)}]  collected {len(raw_fields_list)} entities")

    print(f"\nResolving {len(label_qids)} publisher/award/series labels...")
    label_lookup = resolve_qid_labels(label_qids) if label_qids else {}
    print(f"  Resolved {len(label_lookup)}/{len(label_qids)} labels")

    # Pass 2: derive final field dicts and apply
    n_filled = 0
    n_overwrites = 0
    counters: dict[str, int] = {}
    overwrites_seen: list[tuple[str, dict]] = []

    for path, book, raw in raw_fields_list:
        fields = derive_publisher_label(dict(raw), label_lookup)
        fields = derive_awards(fields, label_lookup)
        fields = derive_series(fields, label_lookup)

        # If first_published from Wikidata exists but is wildly later than
        # what OL gave us, ignore — Wikidata occasionally records "edition
        # date" via P577 instead of first publication. Our own consensus
        # filter (Phase A) already validated OL's number.
        ol_first = book.get("first_published")
        wd_first = fields.get("first_published")
        if (ol_first is not None and wd_first is not None
                and wd_first > ol_first + 1
                and (book.get("_provenance") or {}).get("first_published") == "ol_firstedition_v1"):
            # Wikidata trying to push the year forward against an OL anchor — discard
            fields.pop("first_published", None)
            fields.pop("first_published_circa", None)

        if not fields:
            continue

        for k in fields:
            counters[k] = counters.get(k, 0) + 1

        if args.apply:
            changed, audit = provenance_merge(
                book, fields, source=SOURCE, fields_overwritable=FIELDS_OVERWRITABLE,
            )
            if changed:
                save_json(path, book)
                n_filled += 1
            if audit:
                n_overwrites += len(audit)
                overwrites_seen.append((book["slug"], audit))
        else:
            sim = dict(book); sim["_provenance"] = dict(book.get("_provenance") or {})
            changed, audit = provenance_merge(
                sim, fields, source=SOURCE, fields_overwritable=FIELDS_OVERWRITABLE,
            )
            if changed:
                n_filled += 1
            if audit:
                n_overwrites += len(audit)
                overwrites_seen.append((book["slug"], audit))

    print(f"\nDone. {n_filled} books got new fields. Overwrites: {n_overwrites}.")
    print("\nField fill counts:")
    for k in sorted(counters):
        if k.startswith("_"):
            continue
        print(f"  +{k:30s}  {counters[k]}")

    if args.report_overwrites and overwrites_seen:
        print("\nOverwrite details (first 30):")
        for slug, audit in overwrites_seen[:30]:
            for f, change in audit.items():
                print(
                    f"  {slug:40s}  {f}: {change['from']!r} → {change['to']!r}"
                    f"  ({change['old_source']} → {change['new_source']})"
                )

    if not args.apply:
        print("\nDry-run — pass --apply to write")

    return 0


if __name__ == "__main__":
    sys.exit(main())
