#!/usr/bin/env python3
"""
Apply reading status from data/reading-status.csv to book JSON files.

The CSV is the single source of truth for reading status. Edit it
to mark books as: want, reading, or read. Then rebuild the site.

CSV format:
  slug,status,date_updated,notes
  dune,read,2024-06-15,Classic sci-fi
  neuromancer,want,,On my list

Status values: want | reading | read | (empty = no status)

Usage:
  python scripts/apply-reading-status.py
"""

import csv
import json
from pathlib import Path

BOOKS_DIR = Path(__file__).parent.parent / "src" / "content" / "books"
STATUS_CSV = Path(__file__).parent.parent / "data" / "reading-status.csv"


def main() -> None:
    if not STATUS_CSV.exists():
        print("No reading-status.csv found — skipping")
        return

    # Read status CSV
    statuses: dict[str, dict[str, str]] = {}
    with open(STATUS_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            slug = row.get("slug", "").strip()
            status = row.get("status", "").strip()
            if slug and status:
                statuses[slug] = {
                    "reading_status": status,
                    "status_date": row.get("date_updated", "").strip() or None,
                    "status_notes": row.get("notes", "").strip() or None,
                }

    print(f"Reading status CSV: {len(statuses)} entries")

    # Apply to book JSON files
    applied = 0
    cleared = 0
    for bp in sorted(BOOKS_DIR.glob("*.json")):
        book = json.loads(bp.read_text())
        slug = book.get("slug", bp.stem)

        if slug in statuses:
            entry = statuses[slug]
            changed = False
            for key, value in entry.items():
                if value is not None:
                    if book.get(key) != value:
                        book[key] = value
                        changed = True
                elif key in book:
                    del book[key]
                    changed = True
            if changed:
                bp.write_text(json.dumps(book, indent=2, ensure_ascii=False))
                applied += 1
        else:
            # Clear status if book was previously marked but removed from CSV
            changed = False
            for key in ("reading_status", "status_date", "status_notes"):
                if key in book:
                    del book[key]
                    changed = True
            if changed:
                bp.write_text(json.dumps(book, indent=2, ensure_ascii=False))
                cleared += 1

    print(f"Applied: {applied}, Cleared: {cleared}")

    # Print summary by status
    status_counts: dict[str, int] = {}
    for entry in statuses.values():
        s = entry["reading_status"]
        status_counts[s] = status_counts.get(s, 0) + 1
    for s, c in sorted(status_counts.items()):
        print(f"  {s}: {c}")


if __name__ == "__main__":
    main()
