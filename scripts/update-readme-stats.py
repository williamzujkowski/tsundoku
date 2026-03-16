#!/usr/bin/env python3
"""
Update README.md stats from stats.json.

Replaces content between <!-- STATS:START --> and <!-- STATS:END -->
markers with current numbers. Run after generate-stats.py.

Usage:
  python scripts/update-readme-stats.py
"""

import json
import re
from pathlib import Path

STATS_PATH = Path(__file__).parent.parent / "src" / "data" / "stats.json"
README_PATH = Path(__file__).parent.parent / "README.md"


def main() -> None:
    stats = json.loads(STATS_PATH.read_text())

    books = stats["total_books"]
    categories = stats["total_categories"]
    authors = stats["total_authors"]
    gutenberg = stats["links"]["gutenberg"]
    librivox = stats["links"]["librivox"]
    hathitrust = stats["links"]["hathitrust"]

    readme = README_PATH.read_text()

    # Replace the features line with book/author/category counts
    readme = re.sub(
        r'- \*\*[\d,]+ books\*\* across \*\*\d+ categories\*\* from \*\*[\d,]+ authors\*\*',
        f'- **{books:,} books** across **{categories} categories** from **{authors:,} authors**',
        readme,
    )

    # Replace the free reading links line
    readme = re.sub(
        r'- Free reading/listening links: [\d,]+ Project Gutenberg, [\d,]+ LibriVox audiobooks, [\d,]+ HathiTrust',
        f'- Free reading/listening links: {gutenberg:,} Project Gutenberg, {librivox:,} LibriVox audiobooks, {hathitrust:,} HathiTrust',
        readme,
    )

    README_PATH.write_text(readme)
    print(f"README updated: {books:,} books, {authors:,} authors, {categories} categories")
    print(f"  Links: {gutenberg:,} Gutenberg, {librivox:,} LibriVox, {hathitrust:,} HathiTrust")


if __name__ == "__main__":
    main()
