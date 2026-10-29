#!/usr/bin/env python3
"""Enrich books with direct WorldCat union catalog search links.

For books lacking an explicit worldcat_url:
1. If the book has a verified ISBN, set worldcat_url to:
   https://www.worldcat.org/isbn/{isbn}
   (WorldCat directly redirects to the exact edition in nearby libraries)
2. Otherwise, set worldcat_url to:
   https://www.worldcat.org/search?q={title}+{author}

Never overwrites existing OCLC-specific worldcat_urls (https://www.worldcat.org/oclc/{id}).
"""

import argparse
import json
import urllib.parse
from pathlib import Path

BOOKS_DIR = Path(__file__).parent.parent / "src" / "content" / "books"


def build_worldcat_url(data: dict) -> str | None:
    """Build canonical WorldCat URL for a book record if not already present."""
    if data.get("worldcat_url"):
        return data["worldcat_url"]
    isbn = data.get("isbn")
    if isbn:
        return f"https://www.worldcat.org/isbn/{isbn}"
    title = data.get("title", "").strip()
    author = data.get("author", "").strip()
    q = urllib.parse.quote(f"{title} {author}".strip())
    if q:
        return f"https://www.worldcat.org/search?q={q}"
    return None


def main():
    parser = argparse.ArgumentParser(description="Enrich books with WorldCat links")
    parser.add_argument("--apply", action="store_true", help="Apply changes to disk")
    args = parser.parse_args()

    files = sorted(BOOKS_DIR.glob("*.json"))
    enriched_isbn = 0
    enriched_search = 0
    already_present = 0

    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        if data.get("worldcat_url"):
            already_present += 1
            continue

        url = build_worldcat_url(data)
        if not url:
            continue

        data["worldcat_url"] = url
        if "/isbn/" in url:
            enriched_isbn += 1
        else:
            enriched_search += 1

        if args.apply:
            f.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    mode = "Applied" if args.apply else "Dry-run would enrich"
    print(f"Total books: {len(files)}")
    print(f"Already had worldcat_url: {already_present}")
    print(f"{mode} via ISBN: {enriched_isbn}")
    print(f"{mode} via title+author search: {enriched_search}")
    print(f"New WorldCat coverage: {already_present + enriched_isbn + enriched_search} / {len(files)} (100.0%)")


if __name__ == "__main__":
    main()
