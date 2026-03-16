#!/usr/bin/env python3
"""
Enrich book categories based on subjects, title keywords, and existing data.

Books with generic categories (like "Literature") may belong in more specific
categories based on their subjects. This script suggests recategorizations
based on keyword matching.

Usage:
  python scripts/enrich-categories.py                # dry run
  python scripts/enrich-categories.py --apply        # apply changes
  python scripts/enrich-categories.py --report       # show category stats
"""

import json
import re
from collections import Counter
from pathlib import Path

BOOKS_DIR = Path(__file__).parent.parent / "src" / "content" / "books"

# Subject/title keywords → suggested category
# Only triggers if current category is a "generic" bucket
KEYWORD_RULES: list[tuple[list[str], str]] = [
    # AI / ML → Computer Science
    (["artificial intelligence", "machine learning", "deep learning",
      "neural network", "natural language processing", "reinforcement learning",
      "computer vision", "large language model"], "Computer Science"),

    # Cryptography / Cybersecurity → Security
    (["cryptography", "cybersecurity", "information security", "malware",
      "penetration testing", "network security", "encryption"], "Security"),

    # Physics / Chemistry / Biology → Science (avoid fiction triggers)
    (["quantum mechanics", "quantum physics", "thermodynamics", "relativity",
      "genetics", "molecular biology", "chemistry",
      "astrophysics", "cosmology", "evolutionary biology"], "Science"),

    # Economics
    (["economics", "macroeconomics", "microeconomics", "fiscal",
      "monetary policy", "game theory", "behavioral economics"], "Economics"),

    # Mathematics
    (["algebra", "calculus", "topology", "number theory", "combinatorics",
      "probability", "statistics", "mathematical analysis"], "Mathematics"),
]

# Categories considered "generic" (books might be better placed elsewhere)
GENERIC_CATEGORIES = {
    "Literature",  # Very broad — 1,475 books
    "Classics",    # Often overlaps with other categories
}


def suggest_recategorization(book: dict) -> str | None:
    """Suggest a better category based on subjects and title."""
    current = book.get("category", "")

    # Only recategorize from generic buckets
    if current not in GENERIC_CATEGORIES:
        return None

    # Build searchable text from subjects + title
    subjects = book.get("subjects", [])
    search_text = " ".join(subjects).lower() + " " + book.get("title", "").lower()

    for keywords, target_category in KEYWORD_RULES:
        for kw in keywords:
            # Require word boundary match to avoid "revolution" matching "evolution"
            if re.search(r'\b' + re.escape(kw) + r'\b', search_text):
                return target_category

    return None


def category_report() -> None:
    """Print current category distribution."""
    cats: Counter[str] = Counter()
    for bp in BOOKS_DIR.glob("*.json"):
        book = json.loads(bp.read_text())
        cats[book["category"]] += 1

    print(f"\n{'Category':<35} {'Count':>5}")
    print("-" * 42)
    for cat, count in cats.most_common():
        print(f"{cat:<35} {count:>5}")
    print(f"\nTotal categories: {len(cats)}")


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Enrich book categories from subjects")
    parser.add_argument("--apply", action="store_true", help="Apply changes")
    parser.add_argument("--report", action="store_true", help="Show category stats")
    args = parser.parse_args()

    if args.report:
        category_report()
        return

    changes = []
    for bp in sorted(BOOKS_DIR.glob("*.json")):
        book = json.loads(bp.read_text())
        new_cat = suggest_recategorization(book)
        if new_cat and new_cat != book["category"]:
            changes.append({
                "path": bp,
                "title": book["title"],
                "old": book["category"],
                "new": new_cat,
                "reason": "subject/title keyword match",
            })
            if args.apply:
                book["category"] = new_cat
                bp.write_text(json.dumps(book, indent=2, ensure_ascii=False))

    if not changes:
        print("No recategorizations suggested.")
        print("Tip: Run enrich-gaps.py --field subjects first to populate subjects.")
        return

    print(f"{'Applied' if args.apply else 'Would change'} {len(changes)} books:\n")
    by_change: dict[str, list[str]] = {}
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
