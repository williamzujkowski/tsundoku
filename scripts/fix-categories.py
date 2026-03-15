#!/usr/bin/env python3
"""
Fix category assignments for books in the tsundoku collection.

Consolidates thin categories and recategorizes books based on
title/subject keyword matching.

Usage:
  python scripts/fix-categories.py              # dry run (show changes)
  python scripts/fix-categories.py --apply      # apply changes
"""

import json
import re
from pathlib import Path

BOOKS_DIR = Path(__file__).parent.parent / "src" / "content" / "books"

# Category merges: old → new
CATEGORY_MERGES = {
    "AI": "Computer Science",
    "Security & Governance": "Security",
    "Security & Intelligence": "Security",
    "Intelligence Studies": "Security",
    "Cybernetics": "Complex Systems",
    "Systems": "Complex Systems",
    "Complexity Science": "Complex Systems",
    "Decision Theory": "Mathematics",
    "Political Economy": "Economics",
    "Information Theory": "Mathematics",
    "Strategy": "Political Theory",
    "Psychology": "Science",
    "Politics": "Political Theory",
    "Literary Theory": "Literary Criticism",
}

# Per-book overrides (slug → new category) for specific reassignments
BOOK_OVERRIDES = {
    "capital-vol-1": "Economics",
}

# Keyword → category assignments (checked against title and subjects)
KEYWORD_CATEGORIES = {
    "Computer Science": {
        "keywords": [
            "artificial intelligence", "machine learning", "deep learning",
            "neural network", "natural language processing", "nlp",
            "computer vision", "reinforcement learning", "ai ",
            "tensorflow", "pytorch", "chatgpt", "large language model",
        ],
        "target": "Computer Science",  # keep in CS, don't split
    },
}


def should_recategorize(book: dict) -> str | None:
    """Check if a book should be moved to a different category based on merges."""
    slug = book.get("slug", "")

    # Per-book override takes priority
    if slug in BOOK_OVERRIDES:
        return BOOK_OVERRIDES[slug]

    current = book.get("category", "")

    # Direct merge
    if current in CATEGORY_MERGES:
        return CATEGORY_MERGES[current]

    return None


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Fix book categories")
    parser.add_argument("--apply", action="store_true", help="Apply changes (default: dry run)")
    args = parser.parse_args()

    changes = []
    for bp in sorted(BOOKS_DIR.glob("*.json")):
        book = json.loads(bp.read_text())
        new_cat = should_recategorize(book)

        if new_cat:
            changes.append({
                "path": bp,
                "title": book["title"],
                "old": book["category"],
                "new": new_cat,
            })

            if args.apply:
                book["category"] = new_cat
                bp.write_text(json.dumps(book, indent=2, ensure_ascii=False))

    # Report
    if not changes:
        print("No category changes needed.")
        return

    print(f"{'Applied' if args.apply else 'Would change'} {len(changes)} books:\n")
    by_change = {}
    for c in changes:
        key = f"{c['old']} → {c['new']}"
        by_change.setdefault(key, []).append(c["title"])

    for change, titles in sorted(by_change.items()):
        print(f"  {change} ({len(titles)} books)")
        for t in titles[:5]:
            print(f"    - {t}")
        if len(titles) > 5:
            print(f"    ... and {len(titles) - 5} more")


if __name__ == "__main__":
    main()
