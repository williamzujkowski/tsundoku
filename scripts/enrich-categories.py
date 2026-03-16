#!/usr/bin/env python3
"""
Enrich book categories based on subjects, tags, and title keywords.

Two recategorization strategies (both from generic categories only):
1. Subject/title keywords → non-fiction categories (CS, Security, Science, etc.)
2. Genre tags → fiction categories (Sci-Fi, Fantasy, Mystery, etc.)

Only moves books from generic buckets (Literature, Classics).
Requires exactly 1 strong genre signal to avoid ambiguous moves.

Usage:
  python scripts/enrich-categories.py                # dry run
  python scripts/enrich-categories.py --apply        # apply changes
  python scripts/enrich-categories.py --report       # show category stats
"""

import re
from collections import Counter

from enrichment_config import load_all_books, save_book

# Subject/title keywords → non-fiction category (word boundary matching)
KEYWORD_RULES: list[tuple[list[str], str]] = [
    (["artificial intelligence", "machine learning", "deep learning",
      "neural network", "natural language processing", "reinforcement learning",
      "computer vision", "large language model"], "Computer Science"),
    (["cryptography", "cybersecurity", "information security", "malware",
      "penetration testing", "network security", "encryption"], "Security"),
    (["quantum mechanics", "quantum physics", "thermodynamics", "relativity",
      "genetics", "molecular biology", "chemistry",
      "astrophysics", "cosmology", "evolutionary biology"], "Science"),
    (["economics", "macroeconomics", "microeconomics", "fiscal",
      "monetary policy", "game theory", "behavioral economics"], "Economics"),
    (["algebra", "calculus", "topology", "number theory", "combinatorics",
      "probability", "statistics", "mathematical analysis"], "Mathematics"),
]

# Genre tags → fiction category (requires exactly 1 strong match)
TAG_TO_CATEGORY = {
    "sci-fi": "Science Fiction",
    "fantasy": "Fantasy",
    "mystery": "Mystery",
    "horror": "Horror",
    "historical-fiction": "History",
}

# Categories considered "generic" (books might be better placed)
GENERIC_CATEGORIES = {"Literature", "Classics"}


def suggest_recategorization(book: dict) -> str | None:
    """Suggest a better category based on subjects, tags, and title."""
    current = book.get("category", "")
    if current not in GENERIC_CATEGORIES:
        return None

    # Strategy 1: Subject/title keyword matching (non-fiction)
    subjects = book.get("subjects", [])
    search_text = " ".join(subjects).lower() + " " + book.get("title", "").lower()
    for keywords, target in KEYWORD_RULES:
        for kw in keywords:
            if re.search(r'\b' + re.escape(kw) + r'\b', search_text):
                return target

    # Strategy 2: Genre tag matching (fiction — require exactly 1 strong signal)
    tags = set(book.get("tags", []))
    strong_matches = [(t, c) for t, c in TAG_TO_CATEGORY.items() if t in tags]
    if len(strong_matches) == 1:
        return strong_matches[0][1]

    return None


def category_report() -> None:
    """Print current category distribution."""
    cats: Counter[str] = Counter()
    for _, book in load_all_books():
        cats[book["category"]] += 1

    print(f"\n{'Category':<35} {'Count':>5}")
    print("-" * 42)
    for cat, count in cats.most_common():
        print(f"{cat:<35} {count:>5}")
    print(f"\nTotal categories: {len(cats)}")


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Enrich book categories")
    parser.add_argument("--apply", action="store_true", help="Apply changes")
    parser.add_argument("--report", action="store_true", help="Show category stats")
    args = parser.parse_args()

    if args.report:
        category_report()
        return

    changes: list[dict] = []
    for bp, book in load_all_books():
        new_cat = suggest_recategorization(book)
        if new_cat and new_cat != book["category"]:
            changes.append({"path": bp, "title": book["title"],
                            "old": book["category"], "new": new_cat})
            if args.apply:
                book["category"] = new_cat
                save_book(bp, book)

    if not changes:
        print("No recategorizations suggested.")
        return

    action = "Applied" if args.apply else "Would change"
    print(f"{action} {len(changes)} books:\n")
    by_change: dict[str, list[str]] = {}
    for c in changes:
        key = f"{c['old']} → {c['new']}"
        by_change.setdefault(key, []).append(c["title"])
    for change, titles in sorted(by_change.items()):
        print(f"  {change} ({len(titles)} books)")
        for t in sorted(titles)[:5]:
            print(f"    - {t}")
        if len(titles) > 5:
            print(f"    ... and {len(titles) - 5} more")


if __name__ == "__main__":
    main()
