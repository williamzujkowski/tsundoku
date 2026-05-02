#!/usr/bin/env python3
"""
Multi-source gap filler — identifies missing fields per book and queries
the best source for each gap. Only fills NULL/missing fields, never overwrites.

Sources queried (in priority order per field):
  - description: Google Books → Open Library
  - subjects: Open Library → Google Books
  - pages: Open Library → Google Books
  - isbn: Open Library → Google Books
  - cover_url: Open Library (by title/author)

Usage:
  python scripts/enrich-gaps.py --limit 100          # fill gaps for 100 books
  python scripts/enrich-gaps.py --field description   # only fill descriptions
  python scripts/enrich-gaps.py --report              # show gap report only
"""

import json
import time
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import quote_plus

from enrichment_state import EnrichmentState

BOOKS_DIR = Path(__file__).parent.parent / "src" / "content" / "books"
USER_AGENT = "Tsundoku/1.0 (https://github.com/williamzujkowski/tsundoku)"
RATE_LIMIT = 1.0  # Be conservative across all sources

# Fields we can fill and their priority sources
FILLABLE_FIELDS = {
    "description": ["google_books", "open_library"],
    "subject_facet": ["open_library", "google_books"],
    "pages": ["open_library", "google_books"],
    "isbn": ["open_library", "google_books"],
    "cover_url": ["open_library"],
}


def identify_gaps(book: dict) -> list[str]:
    """Return list of missing fields that can be filled."""
    gaps = []
    for field in FILLABLE_FIELDS:
        val = book.get(field)
        if val is None or val == "" or val == []:
            gaps.append(field)
    return gaps


def query_open_library(title: str, author: str) -> dict:
    """Query Open Library search API for book metadata."""
    query = quote_plus(f"{title} {author}")
    url = f"https://openlibrary.org/search.json?q={query}&fields=title,author_name,subject,number_of_pages_median,isbn,cover_i,first_publish_year&limit=3"

    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            docs = data.get("docs", [])
            if not docs:
                return {}

            # Use first result (best match)
            doc = docs[0]
            result = {}

            subjects = doc.get("subject", [])
            if subjects:
                # Take top 10 subjects, clean up
                result["subject_facet"] = [s for s in subjects[:10] if len(s) < 100]

            pages = doc.get("number_of_pages_median")
            if pages and pages > 0:
                result["pages"] = pages

            isbns = doc.get("isbn", [])
            if isbns:
                # Prefer ISBN-13
                isbn13 = [i for i in isbns if len(i) == 13]
                result["isbn"] = isbn13[0] if isbn13 else isbns[0]

            cover_id = doc.get("cover_i")
            if cover_id:
                result["cover_url"] = f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"
                result["cover_url_large"] = f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"

            return result

    except Exception as e:
        print(f"    OL error: {e}")
    return {}


def query_google_books(title: str, author: str, isbn: str | None = None) -> dict:
    """Query Google Books API for book metadata. No API key needed for basic search."""
    if isbn:
        query = quote_plus(f"isbn:{isbn}")
    else:
        query = quote_plus(f"intitle:{title} inauthor:{author}")
    url = f"https://www.googleapis.com/books/v1/volumes?q={query}&maxResults=1"

    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            items = data.get("items", [])
            if not items:
                return {}

            info = items[0].get("volumeInfo", {})
            result = {}

            desc = info.get("description", "")
            if desc and len(desc) > 20:
                # Strip HTML tags for clean text
                import re
                result["description"] = re.sub(r'<[^>]+>', '', desc).strip()

            pages = info.get("pageCount")
            if pages and pages > 0:
                result["pages"] = pages

            categories = info.get("categories", [])
            if categories:
                result["subject_facet"] = categories

            identifiers = info.get("industryIdentifiers", [])
            for ident in identifiers:
                if ident.get("type") == "ISBN_13":
                    result["isbn"] = ident["identifier"]
                    break
                elif ident.get("type") == "ISBN_10":
                    result["isbn"] = ident["identifier"]

            return result

    except Exception as e:
        print(f"    Google error: {e}")
    return {}


def fill_gaps(book: dict, gaps: list[str]) -> dict:
    """Try to fill missing fields from multiple sources."""
    filled = {}
    title = book["title"]
    author = book["author"]
    isbn = book.get("isbn")

    # Track which sources we've queried to avoid duplicate calls
    source_cache: dict[str, dict] = {}

    for field in gaps:
        sources = FILLABLE_FIELDS.get(field, [])
        for source in sources:
            # Query source if not cached
            if source not in source_cache:
                if source == "open_library":
                    source_cache[source] = query_open_library(title, author)
                    time.sleep(RATE_LIMIT)
                elif source == "google_books":
                    source_cache[source] = query_google_books(title, author, isbn)
                    time.sleep(RATE_LIMIT)

            # Check if this source has the field
            data = source_cache.get(source, {})
            if field in data:
                if field == "subject_facet":
                    # Merge from multiple sources rather than replacing
                    existing = set(book.get("subject_facet") or [])
                    new_facets = set(data[field])
                    merged = sorted(existing | new_facets)
                    if merged != sorted(existing):
                        filled[field] = merged
                else:
                    filled[field] = data[field]
                # Also grab cover_url_large if we got cover_url from OL
                if field == "cover_url" and "cover_url_large" in data:
                    filled["cover_url_large"] = data["cover_url_large"]
                break  # Got it from this source, no need for fallback

    return filled


def gap_report() -> None:
    """Print a report of all missing fields across the collection."""
    from collections import Counter
    field_gaps: Counter[str] = Counter()
    total = 0

    for bp in sorted(BOOKS_DIR.glob("*.json")):
        book = json.loads(bp.read_text())
        total += 1
        gaps = identify_gaps(book)
        for g in gaps:
            field_gaps[g] += 1

    print(f"\n{'Field':<15} {'Missing':>8} {'% Complete':>10}")
    print("-" * 35)
    for field in FILLABLE_FIELDS:
        missing = field_gaps.get(field, 0)
        pct = round(100 * (total - missing) / total, 1)
        print(f"{field:<15} {missing:>8} {pct:>9.1f}%")
    print(f"\nTotal books: {total}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Fill data gaps from multiple sources")
    parser.add_argument("--limit", type=int, default=50, help="Max books to process")
    parser.add_argument("--field", type=str, help="Only fill this specific field")
    parser.add_argument("--report", action="store_true", help="Show gap report only")
    args = parser.parse_args()

    if args.report:
        gap_report()
        return

    state = EnrichmentState("gap-filler")
    book_files = sorted(BOOKS_DIR.glob("*.json"))
    state.set_total_books(len(book_files))

    # Find books with gaps
    candidates = []
    for bp in book_files:
        book = json.loads(bp.read_text())
        gaps = identify_gaps(book)
        if args.field:
            gaps = [g for g in gaps if g == args.field]
        if gaps and state.should_scan(book.get("slug", "")):
            candidates.append((bp, book, gaps))

    print(f"Found {len(candidates)} books with fillable gaps")

    if args.limit > 0:
        candidates = candidates[:args.limit]

    filled_count = 0
    for i, (bp, book, gaps) in enumerate(candidates, 1):
        print(f"[{i}/{len(candidates)}] {book['title'][:50]}... gaps: {','.join(gaps)}", end=" ", flush=True)

        filled = fill_gaps(book, gaps)
        if filled:
            # Only update missing fields
            for key, val in filled.items():
                if key not in book or book[key] is None or book[key] == "" or book[key] == []:
                    book[key] = val

            bp.write_text(json.dumps(book, indent=2, ensure_ascii=False))
            filled_count += 1
            state.record_scan(book.get("slug", ""), matched=True)
            print(f"✓ filled: {','.join(filled.keys())}")
        else:
            state.record_scan(book.get("slug", ""), matched=False)
            print("—")

    state.save()
    print(f"\nDone: {filled_count} books enriched out of {len(candidates)} processed")
    print(state.summary())


if __name__ == "__main__":
    main()
