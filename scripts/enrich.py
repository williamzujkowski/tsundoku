#!/usr/bin/env python3
"""
Enrich book data with descriptions and cover images from Open Library.

Usage:
  python scripts/enrich.py                    # enrich all books missing data
  python scripts/enrich.py --limit 50         # enrich first 50 books
  python scripts/enrich.py --book dune.json   # enrich a specific book

Open Library API (free, no key required):
  Search: https://openlibrary.org/search.json?title=X&author=Y
  Covers: https://covers.openlibrary.org/b/olid/{OLID}-M.jpg
"""

import json
import sys
import time
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError
from urllib.parse import quote_plus

BOOKS_DIR = Path(__file__).parent.parent / "src" / "content" / "books"
USER_AGENT = "Tsundoku/1.0 (https://github.com/williamzujkowski/tsundoku)"
RATE_LIMIT_SECONDS = 1.0  # Be nice to APIs


def search_google_books(title: str, author: str) -> dict | None:
    """Fallback: search Google Books API (free, no key required for basic use)."""
    query = quote_plus(f"{title} {author}")
    url = f"https://www.googleapis.com/books/v1/volumes?q={query}&maxResults=1"

    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            items = data.get("items", [])
            if items:
                return items[0].get("volumeInfo", {})
    except (URLError, TimeoutError, json.JSONDecodeError) as e:
        print(f"  ⚠ Google Books error: {e}")
    return None


def extract_google_metadata(vol: dict) -> dict:
    """Extract metadata from a Google Books volume info."""
    result = {}

    desc = vol.get("description", "")
    if desc:
        # Truncate long descriptions
        result["description"] = desc[:500] + ("..." if len(desc) > 500 else "")

    # Cover image
    images = vol.get("imageLinks", {})
    thumb = images.get("thumbnail", "")
    if thumb:
        # Google returns http:// URLs — upgrade to https
        thumb = thumb.replace("http://", "https://")
        result["cover_url"] = thumb
        # Try to get larger image
        large = images.get("medium") or images.get("small") or thumb
        result["cover_url_large"] = large.replace("http://", "https://")

    # ISBN
    for identifier in vol.get("industryIdentifiers", []):
        if identifier.get("type") in ("ISBN_13", "ISBN_10"):
            result["isbn"] = identifier["identifier"]
            break

    # Published date
    pub_date = vol.get("publishedDate", "")
    if pub_date:
        try:
            result["first_published"] = int(pub_date[:4])
        except ValueError:
            pass

    # Pages
    pages = vol.get("pageCount")
    if pages:
        result["pages"] = pages

    # Categories as subjects
    cats = vol.get("categories", [])
    if cats:
        result["subjects"] = cats[:5]

    # Language
    lang = vol.get("language")
    if lang:
        result["language"] = lang

    # Google Books link
    info_link = vol.get("infoLink")
    if info_link:
        result["google_books_url"] = info_link

    return result


def search_open_library(title: str, author: str) -> dict | None:
    """Search Open Library for a book by title and author."""
    query = f"title={quote_plus(title)}&author={quote_plus(author)}&limit=1"
    url = f"https://openlibrary.org/search.json?{query}"

    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            docs = data.get("docs", [])
            if docs:
                return docs[0]
    except (URLError, TimeoutError, json.JSONDecodeError) as e:
        print(f"  ⚠ API error: {e}")
    return None


def extract_metadata(doc: dict) -> dict:
    """Extract useful metadata from an Open Library search result."""
    result = {}

    # Description
    # Open Library search results don't include full descriptions,
    # but they have first_sentence and subject
    first_sentence = doc.get("first_sentence", [])
    if first_sentence:
        result["description"] = first_sentence[0] if isinstance(first_sentence, list) else str(first_sentence)

    # Cover
    cover_i = doc.get("cover_i")
    if cover_i:
        result["cover_url"] = f"https://covers.openlibrary.org/b/id/{cover_i}-M.jpg"
        result["cover_url_large"] = f"https://covers.openlibrary.org/b/id/{cover_i}-L.jpg"

    # Open Library ID
    olid = doc.get("key", "")
    if olid:
        result["open_library_url"] = f"https://openlibrary.org{olid}"

    # ISBN
    isbns = doc.get("isbn", [])
    if isbns:
        result["isbn"] = isbns[0]

    # First publish year
    first_year = doc.get("first_publish_year")
    if first_year:
        result["first_published"] = first_year

    # Subjects
    subjects = doc.get("subject", [])
    if subjects:
        result["subjects"] = subjects[:5]  # Keep top 5

    # Number of pages (from first edition)
    pages = doc.get("number_of_pages_median")
    if pages:
        result["pages"] = pages

    # Language
    languages = doc.get("language", [])
    if languages:
        result["language"] = languages[0]

    return result


def enrich_book(book_path: Path, force: bool = False) -> bool:
    """Enrich a single book file with Open Library data."""
    with open(book_path) as f:
        book = json.load(f)

    # Skip if already enriched (has cover_url) unless force
    if not force and book.get("cover_url"):
        return False

    title = book["title"]
    author = book["author"]

    print(f"  📖 {title} by {author}...", end=" ", flush=True)

    # Try Open Library first
    doc = search_open_library(title, author)
    metadata = extract_metadata(doc) if doc else {}

    # Fallback to Google Books if Open Library missed key data
    if not metadata.get("cover_url"):
        time.sleep(0.5)  # Brief pause between APIs
        gvol = search_google_books(title, author)
        if gvol:
            gmeta = extract_google_metadata(gvol)
            # Merge: Google fills gaps, doesn't overwrite Open Library data
            for key, value in gmeta.items():
                if key not in metadata:
                    metadata[key] = value

    if not metadata:
        print("not found (both APIs)")
        return False

    # Merge metadata into book (don't overwrite existing fields)
    updated = False
    for key, value in metadata.items():
        if key not in book or (force and key in metadata):
            book[key] = value
            updated = True

    if updated:
        with open(book_path, "w") as f:
            json.dump(book, f, indent=2, ensure_ascii=False)
        fields = ", ".join(metadata.keys())
        print(f"✓ ({fields})")
    else:
        print("already complete")

    return updated


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Enrich book data from Open Library")
    parser.add_argument("--limit", type=int, default=0, help="Max books to enrich (0=all)")
    parser.add_argument("--book", type=str, help="Enrich a specific book file")
    parser.add_argument("--force", action="store_true", help="Re-enrich already enriched books")
    parser.add_argument("--priority", type=int, default=0, help="Only enrich books with this priority")
    args = parser.parse_args()

    if args.book:
        book_path = BOOKS_DIR / args.book
        if not book_path.exists():
            print(f"Book not found: {book_path}")
            sys.exit(1)
        enrich_book(book_path, force=args.force)
        return

    # Get all book files
    book_files = sorted(BOOKS_DIR.glob("*.json"))
    print(f"Found {len(book_files)} books")

    # Filter by priority if specified
    if args.priority > 0:
        filtered = []
        for f in book_files:
            with open(f) as fh:
                data = json.load(fh)
                if data.get("priority") == args.priority:
                    filtered.append(f)
        book_files = filtered
        print(f"Filtered to {len(book_files)} priority {args.priority} books")

    # Filter to unenriched books (no cover_url)
    if not args.force:
        unenriched = []
        for f in book_files:
            with open(f) as fh:
                data = json.load(fh)
                if not data.get("cover_url"):
                    unenriched.append(f)
        book_files = unenriched
        print(f"{len(book_files)} books need enrichment")

    if args.limit > 0:
        book_files = book_files[:args.limit]
        print(f"Limited to {len(book_files)} books")

    enriched = 0
    errors = 0
    for i, book_path in enumerate(book_files, 1):
        print(f"[{i}/{len(book_files)}]", end="")
        try:
            if enrich_book(book_path, force=args.force):
                enriched += 1
        except Exception as e:
            print(f" ✗ Error: {e}")
            errors += 1

        time.sleep(RATE_LIMIT_SECONDS)

    print(f"\nDone: {enriched} enriched, {errors} errors, {len(book_files) - enriched - errors} skipped")


if __name__ == "__main__":
    main()
