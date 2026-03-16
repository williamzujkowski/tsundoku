#!/usr/bin/env python3
"""
Smart recategorization of books from Literature to genre categories.

Moves books from the generic "Literature" category to specific genre
categories when there's a strong signal from tags/subjects. Books with
ambiguous or multiple genre signals stay in Literature.

Usage:
  python scripts/recategorize-literature.py           # dry run
  python scripts/recategorize-literature.py --apply   # apply changes
"""

import json
from collections import Counter
from pathlib import Path

BOOKS_DIR = Path(__file__).parent.parent / "src" / "content" / "books"

# Tag → target category mapping (only strong, unambiguous mappings)
TAG_TO_CATEGORY = {
    "sci-fi": "Science Fiction",
    "fantasy": "Fantasy",
    "mystery": "Mystery",
    "horror": "Horror",
    "historical-fiction": "History",
}

# Tags that should NOT trigger recategorization (too broad or ambiguous)
WEAK_TAGS = {"adventure", "humor", "satire", "romance", "thriller", "drama",
             "poetry", "essays", "short-stories", "children", "young-adult"}


def suggest_category(book: dict) -> str | None:
    """Suggest a better category for a Literature book based on tags."""
    if book.get("category") != "Literature":
        return None

    tags = set(book.get("tags", []))
    if not tags:
        return None

    # Only recategorize if there's exactly ONE strong genre signal
    strong_matches = []
    for tag, category in TAG_TO_CATEGORY.items():
        if tag in tags:
            strong_matches.append((tag, category))

    # Exactly one strong match = unambiguous recategorization
    if len(strong_matches) == 1:
        return strong_matches[0][1]

    # Multiple strong matches = ambiguous, keep in Literature
    # (e.g., a book tagged both "sci-fi" and "mystery")
    return None


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Recategorize Literature books by genre")
    parser.add_argument("--apply", action="store_true", help="Apply changes")
    args = parser.parse_args()

    changes: list[dict] = []
    for bp in sorted(BOOKS_DIR.glob("*.json")):
        book = json.loads(bp.read_text())
        new_cat = suggest_category(book)
        if new_cat:
            changes.append({
                "path": bp,
                "title": book["title"],
                "old": book["category"],
                "new": new_cat,
                "tags": book.get("tags", []),
            })
            if args.apply:
                book["category"] = new_cat
                bp.write_text(json.dumps(book, indent=2, ensure_ascii=False))

    if not changes:
        print("No recategorizations suggested.")
        return

    action = "Applied" if args.apply else "Would change"
    print(f"{action} {len(changes)} books:\n")

    by_cat: dict[str, list[str]] = {}
    for c in changes:
        key = f"Literature → {c['new']}"
        by_cat.setdefault(key, []).append(c["title"])

    for change, titles in sorted(by_cat.items()):
        print(f"  {change} ({len(titles)} books)")
        for t in sorted(titles)[:8]:
            print(f"    - {t}")
        if len(titles) > 8:
            print(f"    ... and {len(titles) - 8} more")


if __name__ == "__main__":
    main()
