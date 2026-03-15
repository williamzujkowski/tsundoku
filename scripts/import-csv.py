#!/usr/bin/env python3
"""Import seed CSV into individual JSON content files for Astro."""

import csv
import json
import re
import os
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
CSV_PATH = PROJECT_ROOT / "data" / "seed.csv"
OUTPUT_DIR = PROJECT_ROOT / "src" / "content" / "books"


def slugify(text: str) -> str:
    """Convert text to kebab-case slug."""
    text = text.lower()
    text = re.sub(r"[''']", "", text)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return text


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Clear existing files
    for f in OUTPUT_DIR.glob("*.json"):
        f.unlink()

    slug_counts: dict[str, int] = {}
    books_written = 0

    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            title = row["Title"].strip()
            author = row["Author"].strip()
            category = row["Category"].strip()
            priority = int(row["Priority"].strip())

            base_slug = slugify(title)
            if not base_slug:
                base_slug = "untitled"

            if base_slug in slug_counts:
                slug_counts[base_slug] += 1
                slug = f"{base_slug}-{slug_counts[base_slug]}"
            else:
                slug_counts[base_slug] = 1
                slug = base_slug

            book = {
                "title": title,
                "author": author,
                "category": category,
                "priority": priority,
                "slug": slug,
                "tags": [],
            }

            out_path = OUTPUT_DIR / f"{slug}.json"
            with open(out_path, "w", encoding="utf-8") as out:
                json.dump(book, out, indent=2, ensure_ascii=False)

            books_written += 1

    print(f"Imported {books_written} books into {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
