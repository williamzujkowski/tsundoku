#!/usr/bin/env python3
"""
Generate stub author pages for all authors referenced in books
but missing from src/content/authors/.

Creates minimal JSON files with name, slug, and book_count.
Run enrich-authors.py afterward to fetch Wikipedia data.

Usage:
  python scripts/generate-author-stubs.py
"""

import json
import re
from collections import Counter
from pathlib import Path

BOOKS_DIR = Path(__file__).parent.parent / "src" / "content" / "books"
AUTHORS_DIR = Path(__file__).parent.parent / "src" / "content" / "authors"


def to_slug(text: str) -> str:
    """Convert text to URL-safe slug."""
    return re.sub(r'(^-|-$)', '', re.sub(r'[^a-z0-9]+', '-', text.lower()))


def main() -> None:
    # Collect all authors from books
    author_counts: Counter[str] = Counter()
    for bp in BOOKS_DIR.glob("*.json"):
        book = json.loads(bp.read_text())
        author_counts[book["author"]] += 1

    # Find existing author slugs
    existing_slugs = set()
    for ap in AUTHORS_DIR.glob("*.json"):
        author = json.loads(ap.read_text())
        existing_slugs.add(author.get("slug", ""))

    # Generate stubs for missing authors
    created = 0
    skipped_unknown = 0
    for name, count in sorted(author_counts.items()):
        slug = to_slug(name)

        # Skip "Unknown" — not a real author
        if name == "Unknown":
            skipped_unknown += count
            continue

        # Skip authors whose names produce empty slugs (e.g., Cyrillic-only names)
        if not slug:
            continue

        # Skip if page already exists
        if slug in existing_slugs:
            continue

        # Check if file already exists by path
        author_path = AUTHORS_DIR / f"{slug}.json"
        if author_path.exists():
            continue

        author_data = {
            "name": name,
            "slug": slug,
            "book_count": count,
        }

        author_path.write_text(json.dumps(author_data, indent=2, ensure_ascii=False))
        created += 1

    total_authors = len(author_counts)
    print(f"Authors in books: {total_authors}")
    print(f"Already had pages: {len(existing_slugs)}")
    print(f"Created stubs: {created}")
    if skipped_unknown:
        print(f"Skipped 'Unknown': {skipped_unknown} books")


if __name__ == "__main__":
    main()
