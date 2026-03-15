#!/usr/bin/env python3
"""
Enrich book data with Project Gutenberg links.

Uses the Gutendex API (free, no key required):
  https://gutendex.com/books/?search={title}

Adds gutenberg_url and gutenberg_id fields to book JSON files.

Usage:
  python scripts/enrich-gutenberg.py              # enrich all books
  python scripts/enrich-gutenberg.py --limit 500  # batch size
"""

import json
import time
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import quote_plus

from matching import author_last_name, titles_match

BOOKS_DIR = Path(__file__).parent.parent / "src" / "content" / "books"
USER_AGENT = "Tsundoku/1.0 (https://github.com/williamzujkowski/tsundoku)"
RATE_LIMIT = 0.5  # Gutendex is generous but be nice


def search_gutenberg(title: str, author: str) -> dict | None:
    """Search Gutendex for a book by title AND author.

    Requires both title similarity AND author match to prevent
    false positives (e.g., matching an unrelated book with the
    same title by a different author).
    """
    query = quote_plus(f"{title} {author}")
    url = f"https://gutendex.com/books/?search={query}"

    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            results = data.get("results", [])
            if not results:
                return None

            last_name = author_last_name(author)

            for result in results[:5]:
                result_title = result.get("title", "")
                # REQUIRE author match
                author_matched = False
                for a in result.get("authors", []):
                    name = a.get("name", "").lower()
                    if last_name and last_name in name:
                        author_matched = True
                        break

                if not author_matched:
                    continue

                # REQUIRE title similarity
                if titles_match(title, result_title):
                    return result

    except Exception as e:
        print(f"  ⚠ Gutenberg error: {e}")
    return None


def enrich_book(book_path: Path) -> bool:
    """Add Gutenberg link to a book if found."""
    with open(book_path) as f:
        book = json.load(f)

    # Skip if already has Gutenberg URL
    if book.get("gutenberg_url"):
        return False

    title = book["title"]
    author = book["author"]

    result = search_gutenberg(title, author)
    if not result:
        return False

    gid = result.get("id")
    if not gid:
        return False

    book["gutenberg_id"] = gid
    book["gutenberg_url"] = f"https://www.gutenberg.org/ebooks/{gid}"

    # Get formats for reading
    formats = result.get("formats", {})
    if "text/html" in formats:
        book["gutenberg_read_url"] = formats["text/html"]
    elif "text/html; charset=utf-8" in formats:
        book["gutenberg_read_url"] = formats["text/html; charset=utf-8"]

    with open(book_path, "w") as f:
        json.dump(book, f, indent=2, ensure_ascii=False)

    return True


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Enrich books with Gutenberg links")
    parser.add_argument("--limit", type=int, default=0, help="Max books to process")
    args = parser.parse_args()

    book_files = sorted(BOOKS_DIR.glob("*.json"))
    # Filter to books without gutenberg_url
    unenriched = []
    for f in book_files:
        d = json.loads(f.read_text())
        if not d.get("gutenberg_url"):
            unenriched.append(f)

    print(f"Found {len(unenriched)} books without Gutenberg links")

    if args.limit > 0:
        unenriched = unenriched[: args.limit]

    found = 0
    for i, bp in enumerate(unenriched, 1):
        d = json.loads(bp.read_text())
        print(f"[{i}/{len(unenriched)}] {d['title']}...", end=" ", flush=True)

        if enrich_book(bp):
            found += 1
            print("✓ found on Gutenberg")
        else:
            print("—")

        time.sleep(RATE_LIMIT)

    print(f"\nDone: {found} Gutenberg links added out of {len(unenriched)} searched")


if __name__ == "__main__":
    main()
