#!/usr/bin/env python3
"""Generate stub author pages for every author referenced in books.

For each book's `author` field we attribute the book to:
  - The full author string (existing behavior — preserves joint-string records like
    "Robert Jordan & Brandon Sanderson" so old URLs still work)
  - Each individual component name when the string is a multi-author entry like
    "Robert Jordan & Brandon Sanderson" → also stub "Robert Jordan" + "Brandon Sanderson"

Component splitting matches the parseAuthors() helper in src/utils/formatting.ts:
each part must be at least two whitespace-separated tokens (avoids splitting
initials).

Run enrich-authors.py + enrich-authors-gaps.py afterward to populate bios + photos.

Usage:
  python scripts/generate-author-stubs.py
"""

import json
import re
from collections import Counter
from pathlib import Path

BOOKS_DIR = Path(__file__).parent.parent / "src" / "content" / "books"
AUTHORS_DIR = Path(__file__).parent.parent / "src" / "content" / "authors"

# Mirror src/utils/formatting.ts — keep in sync.
STRONG_SEPARATORS = re.compile(r"\s*(?:&| and | with |/)\s*", re.IGNORECASE)
COMMA_SEPARATOR = re.compile(r"\s*,\s*")


def to_slug(text: str) -> str:
    """Convert text to URL-safe slug."""
    return re.sub(r"(^-|-$)", "", re.sub(r"[^a-z0-9]+", "-", text.lower()))


def split_authors(name: str) -> list[str]:
    """Split a multi-author byline into component names. Returns [name] if not joint."""
    strong = [p.strip() for p in STRONG_SEPARATORS.split(name) if p.strip()]
    if len(strong) >= 2:
        return strong
    # Comma is ambiguous; only split when each part has 2+ tokens.
    comma = [p.strip() for p in COMMA_SEPARATOR.split(name) if p.strip() and len(p.split()) >= 2]
    if len(comma) >= 2:
        return comma
    return [name]


def main() -> None:
    # Per book, attribute to BOTH the full author string AND each component name.
    # Use a set per book so a name doesn't double-count if it appears as both
    # full-string and component (rare but possible).
    counts: Counter[str] = Counter()
    for bp in BOOKS_DIR.glob("*.json"):
        book = json.loads(bp.read_text())
        author_str = book["author"]
        names = {author_str, *split_authors(author_str)}
        for n in names:
            counts[n] += 1

    # Find existing author slugs.
    existing_slugs: set[str] = set()
    for ap in AUTHORS_DIR.glob("*.json"):
        author = json.loads(ap.read_text())
        existing_slugs.add(author.get("slug", ""))

    created = 0
    skipped_unknown = 0
    skipped_existing = 0
    for name, count in sorted(counts.items()):
        slug = to_slug(name)

        if name == "Unknown":
            skipped_unknown += count
            continue

        if not slug:
            continue  # cyrillic-only names, etc.

        if slug in existing_slugs:
            skipped_existing += 1
            continue

        author_path = AUTHORS_DIR / f"{slug}.json"
        if author_path.exists():
            skipped_existing += 1
            continue

        author_data = {
            "name": name,
            "slug": slug,
            "book_count": count,
        }
        author_path.write_text(json.dumps(author_data, indent=2, ensure_ascii=False))
        created += 1

    total_authors = len(counts)
    print(f"Distinct author identities (full strings + components): {total_authors}")
    print(f"Existing pages: {skipped_existing}")
    print(f"Created stubs: {created}")
    if skipped_unknown:
        print(f"Skipped 'Unknown': {skipped_unknown} books")


if __name__ == "__main__":
    main()
