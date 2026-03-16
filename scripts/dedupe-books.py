#!/usr/bin/env python3
"""
Find and merge duplicate books (same author, similar title).

Detects:
- Exact duplicates: same title + author
- Article variants: "The X" vs "X", "A X" vs "X"
- Edition variants: "X 3rd Edition" vs "X"
- Subtitle variants: "X: Complete Text" vs "X"

Merge strategy: keep the entry with MORE enrichment data, transfer
any unique fields from the duplicate, delete the duplicate file.

Usage:
  python scripts/dedupe-books.py           # dry run (show duplicates)
  python scripts/dedupe-books.py --apply   # merge and delete duplicates
"""

import json
import re
from collections import defaultdict
from pathlib import Path

BOOKS_DIR = Path(__file__).parent.parent / "src" / "content" / "books"

# Enrichment fields that indicate data quality (more = better entry to keep)
ENRICHMENT_FIELDS = [
    "description", "cover_url", "isbn", "first_published", "subjects",
    "pages", "gutenberg_url", "librivox_url", "hathitrust_url",
    "worldcat_url", "oclc_id", "tags",
]

# Patterns to strip for normalization
EDITION_PATTERNS = [
    r'\s*\d+(?:st|nd|rd|th)\s+edition\s*',
    r'\s*complete\s+text\s*',
    r'\s*unabridged\s*',
    r'\s*\(.*?\)\s*',
]


def normalize_title(title: str) -> str:
    """Normalize a title for comparison."""
    t = title.lower().strip()
    # Strip leading articles
    for article in ("the ", "a ", "an "):
        if t.startswith(article):
            t = t[len(article):]
            break
    # Strip edition/format suffixes
    for pattern in EDITION_PATTERNS:
        t = re.sub(pattern, '', t, flags=re.IGNORECASE)
    return t.strip()


def enrichment_score(book: dict) -> int:
    """Count how many enrichment fields are populated."""
    score = 0
    for field in ENRICHMENT_FIELDS:
        val = book.get(field)
        if val and val != [] and val != "":
            score += 1
    return score


def merge_books(keep: dict, remove: dict) -> dict:
    """Merge fields from remove into keep (only fill missing fields)."""
    for key, val in remove.items():
        if key in ("slug", "title"):
            continue  # Don't overwrite identity fields
        existing = keep.get(key)
        if (existing is None or existing == "" or existing == []) and val:
            keep[key] = val
        elif isinstance(existing, list) and isinstance(val, list):
            # Merge arrays
            merged = sorted(set(existing) | set(val))
            if merged != sorted(existing):
                keep[key] = merged
    return keep


def find_duplicates() -> list[tuple[Path, dict, Path, dict]]:
    """Find duplicate book pairs. Returns (keep_path, keep_book, remove_path, remove_book)."""
    books = []
    for bp in sorted(BOOKS_DIR.glob("*.json")):
        books.append((bp, json.loads(bp.read_text())))

    # Group by normalized title + author
    groups: dict[tuple[str, str], list[tuple[Path, dict]]] = defaultdict(list)
    for bp, b in books:
        key = (normalize_title(b["title"]), b["author"].lower().strip())
        groups[key].append((bp, b))

    duplicates = []
    for key, entries in groups.items():
        if len(entries) < 2:
            continue
        # Sort by enrichment score — keep the best
        entries.sort(key=lambda x: enrichment_score(x[1]), reverse=True)
        keep_path, keep_book = entries[0]
        for remove_path, remove_book in entries[1:]:
            duplicates.append((keep_path, keep_book, remove_path, remove_book))

    return duplicates


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Find and merge duplicate books")
    parser.add_argument("--apply", action="store_true", help="Merge and delete duplicates")
    args = parser.parse_args()

    duplicates = find_duplicates()

    if not duplicates:
        print("No duplicates found.")
        return

    print(f"Found {len(duplicates)} duplicate pairs:\n")
    for keep_path, keep_book, remove_path, remove_book in duplicates:
        ks = enrichment_score(keep_book)
        rs = enrichment_score(remove_book)
        print(f"  KEEP:   \"{keep_book['title']}\" (score={ks}, slug={keep_book['slug']})")
        print(f"  REMOVE: \"{remove_book['title']}\" (score={rs}, slug={remove_book['slug']})")

        if args.apply:
            # Merge fields from remove into keep
            merged = merge_books(keep_book, remove_book)
            keep_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False))
            remove_path.unlink()
            print(f"  → Merged and deleted {remove_path.name}")
        print()

    action = "Merged" if args.apply else "Would merge"
    print(f"{action} {len(duplicates)} duplicate pairs")


if __name__ == "__main__":
    main()
