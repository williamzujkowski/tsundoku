#!/usr/bin/env python3
"""
Enrich book data with LibriVox free audiobook links.

Uses the LibriVox API (free, no key required):
  https://librivox.org/api/feed/audiobooks/?title={title}&format=json

Adds librivox_url field to book JSON files.

Usage:
  python scripts/enrich-librivox.py              # enrich all books
  python scripts/enrich-librivox.py --limit 500  # batch size
"""

import json
import time
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import quote_plus

from matching import strip_article, author_last_name, titles_match

BOOKS_DIR = Path(__file__).parent.parent / "src" / "content" / "books"
USER_AGENT = "Tsundoku/1.0 (https://github.com/williamzujkowski/tsundoku)"
RATE_LIMIT = 1.0  # Be polite to LibriVox


def search_librivox(title: str, author: str) -> dict | None:
    """Search LibriVox for an audiobook by title AND author.

    Requires both title AND author match to prevent false positives.
    """
    if len(title) < 3:
        return None
    search_title = strip_article(title).lower()
    query = quote_plus(search_title)
    url = f"https://librivox.org/api/feed/audiobooks?title={query}&format=json"

    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=15) as resp:
            text = resp.read().decode("utf-8")
            if '"error"' in text[:50]:
                return None
            data = json.loads(text)
            books = data.get("books", [])
            if not books:
                return None

            last_name = author_last_name(author)

            for book in books[:10]:
                result_title = book.get("title", "")
                # REQUIRE author match
                for a in book.get("authors", []):
                    name = f"{a.get('first_name', '')} {a.get('last_name', '')}".lower().strip()
                    if last_name and last_name in name:
                        if titles_match(title, result_title):
                            return book

    except Exception as e:
        print(f"  ⚠ LibriVox error: {e}")
    return None


def enrich_book(book_path: Path) -> bool:
    """Add LibriVox link to a book if found."""
    with open(book_path) as f:
        book = json.load(f)

    # Skip if already has LibriVox URL
    if book.get("librivox_url"):
        return False

    title = book["title"]
    author = book["author"]

    result = search_librivox(title, author)
    if not result:
        return False

    url_librivox = result.get("url_librivox", "")
    if not url_librivox:
        return False

    book["librivox_url"] = url_librivox

    with open(book_path, "w") as f:
        json.dump(book, f, indent=2, ensure_ascii=False)

    return True


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Enrich books with LibriVox audiobook links")
    parser.add_argument("--limit", type=int, default=0, help="Max books to process")
    args = parser.parse_args()

    book_files = sorted(BOOKS_DIR.glob("*.json"))
    unenriched = []
    for f in book_files:
        d = json.loads(f.read_text())
        if not d.get("librivox_url"):
            unenriched.append(f)

    print(f"Found {len(unenriched)} books without LibriVox links")

    if args.limit > 0:
        unenriched = unenriched[: args.limit]

    found = 0
    for i, bp in enumerate(unenriched, 1):
        d = json.loads(bp.read_text())
        print(f"[{i}/{len(unenriched)}] {d['title']}...", end=" ", flush=True)

        if enrich_book(bp):
            found += 1
            print("✓ found on LibriVox")
        else:
            print("—")

        time.sleep(RATE_LIMIT)

    print(f"\nDone: {found} LibriVox links added out of {len(unenriched)} searched")


if __name__ == "__main__":
    main()
