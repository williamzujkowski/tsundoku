#!/usr/bin/env python3
"""Enrich each book with Open Library classification data: DDC, LCC, ISBN.

The original enrich.py pulls cover/year/subjects but doesn't capture the
library classification systems (Dewey, LC). Those are much more reliable
signals for categorization than free-text tags or subjects (#113).

This script also fills missing ISBNs — 14% of our catalog (mostly pre-1970
titles + a long tail of modern books) is currently missing an ISBN, and
OL almost always has at least one for each work via reprint editions.

Goes through scripts/http_cache.py (#91) for politeness; goes through
json_merge.additive_merge so existing fields are never overwritten (#90).

Usage:
  python scripts/enrich-ol-classification.py             # dry-run report
  python scripts/enrich-ol-classification.py --apply     # write changes
  python scripts/enrich-ol-classification.py --apply --limit 50
  python scripts/enrich-ol-classification.py --missing-isbn-only --apply
"""

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.parse import quote_plus

sys.path.insert(0, str(Path(__file__).parent))

from enrichment_config import BOOKS_DIR, USER_AGENT
from http_cache import cached_fetch
from http_retry import fetch_json
from json_merge import additive_merge, save_json
from matching import verify_ol_work_match


REQUEST_TIMEOUT = 15
RATE_LIMIT_S = 0.4

OL_SEARCH = "https://openlibrary.org/search.json"
FIELDS = ",".join([
    "key", "title", "author_name",
    "isbn",                    # array of all known ISBNs (we take the first)
    "ddc",                     # Dewey Decimal Classification array
    "lcc",                     # Library of Congress Classification array
    "subject_facet",           # cleaner / faceted subject list
    "first_publish_year",      # earliest known publication year
    "language",                # 3-letter language codes (we keep first)
    "number_of_pages_median",  # page count from median across editions
])


def _fetch(url: str) -> dict | None:
    return fetch_json(url, timeout=REQUEST_TIMEOUT)


def fetch_ol_work(*, isbn: str | None, title: str, author: str) -> dict | None:
    """Fetch the work record for a book. Prefers ISBN search; falls back to title+author."""
    # ISBN search returns the matching edition's work (most precise)
    if isbn:
        url = f"{OL_SEARCH}?q=isbn:{quote_plus(isbn)}&fields={FIELDS}&limit=1"
        cache_key = f"isbn:{isbn}"
    else:
        # title + author search — use double-quoted phrases for tighter match
        url = (
            f"{OL_SEARCH}"
            f"?title={quote_plus(title)}&author={quote_plus(author)}"
            f"&fields={FIELDS}&limit=3"
        )
        cache_key = f"ta:{title}|{author}"

    # Cache namespace bumped to v2 when we expanded FIELDS (added language,
    # number_of_pages_median). Old responses don't have those fields.
    data = cached_fetch("open_library_work_v2", cache_key, lambda: _fetch(url), url=url)
    if not data:
        return None
    docs = data.get("docs") or []
    return docs[0] if docs else None


def extract_useful_fields(work: dict, current_book: dict) -> dict:
    """Pull out fields we can additive-merge into the book JSON.

    Per #113 user directive: use OL as authoritative for metadata once we
    have the structured IDs. additive_merge guarantees nothing existing is
    overwritten — only fills gaps.

    Refuses to map any field if the work's title/author don't match the
    book's — preventing the cross-record key sharing seen in the
    `ol_work_key` collision audit (e.g. all 4 Marx Capital volumes wound
    up with /works/OL27973414W from a too-loose ISBN→work map).
    """
    if not work:
        return {}
    ok, reason = verify_ol_work_match(
        book_title=current_book.get("title", ""),
        book_author=current_book.get("author", ""),
        work_title=work.get("title", ""),
        work_authors=work.get("author_name") or [],
    )
    if not ok:
        return {}
    out: dict = {}

    # ISBN — only fill if missing; prefer ISBN-13 over ISBN-10
    if not current_book.get("isbn"):
        isbns = work.get("isbn") or []
        isbn13 = [i for i in isbns if len(i) == 13]
        chosen = isbn13[0] if isbn13 else (isbns[0] if isbns else None)
        if chosen:
            out["isbn"] = chosen

    # DDC + LCC — array fields, store as-is
    if work.get("ddc"):
        out["ddc"] = work["ddc"]
    if work.get("lcc"):
        out["lcc"] = work["lcc"]

    # Subject_facet — cleaner than free-text subjects
    if work.get("subject_facet"):
        out["subject_facet"] = work["subject_facet"]

    # First publish year — use OL as authoritative when we don't have one
    if not current_book.get("first_published"):
        year = work.get("first_publish_year")
        if year:
            out["first_published"] = int(year)

    # Language — first one OL returns (usually most common across editions)
    if not current_book.get("language"):
        langs = work.get("language") or []
        if langs:
            out["language"] = langs[0]

    # Page count — OL median across editions
    if not current_book.get("pages"):
        pages = work.get("number_of_pages_median")
        if pages and isinstance(pages, int) and pages > 0:
            out["pages"] = pages

    # OL work key for future reference
    if work.get("key") and not current_book.get("ol_work_key"):
        out["ol_work_key"] = work["key"]

    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Enrich books with OL classification data")
    parser.add_argument("--apply", action="store_true", help="Write changes to disk")
    parser.add_argument("--limit", type=int, default=0, help="Process at most N books")
    parser.add_argument(
        "--missing-isbn-only",
        action="store_true",
        help="Only process books currently missing an ISBN",
    )
    parser.add_argument(
        "--missing-classification-only",
        action="store_true",
        help="Only process books currently missing both ddc and lcc",
    )
    parser.add_argument(
        "--missing-any",
        action="store_true",
        help="Process books missing ANY enrichable field (isbn, ddc, lcc, first_published, language, pages)",
    )
    args = parser.parse_args()

    enrichable_fields = ("isbn", "ddc", "lcc", "first_published", "language", "pages")

    files = sorted(BOOKS_DIR.glob("*.json"))
    candidates: list[tuple[Path, dict]] = []
    for f in files:
        b = json.loads(f.read_text(encoding="utf-8"))
        if args.missing_isbn_only and b.get("isbn"):
            continue
        if args.missing_classification_only and (b.get("ddc") or b.get("lcc")):
            continue
        if args.missing_any and all(b.get(field) for field in enrichable_fields):
            continue
        candidates.append((f, b))

    if args.limit:
        candidates = candidates[: args.limit]

    print(f"Processing {len(candidates)} books")

    n_filled = 0
    n_isbn_added = 0
    n_ddc_added = 0
    n_lcc_added = 0
    n_year_added = 0
    n_lang_added = 0
    n_pages_added = 0
    n_no_match = 0

    for i, (path, book) in enumerate(candidates, 1):
        title = book.get("title", "")
        author = book.get("author", "")
        isbn = book.get("isbn")

        work = fetch_ol_work(isbn=isbn, title=title, author=author)
        time.sleep(RATE_LIMIT_S)

        if not work:
            n_no_match += 1
            if i % 25 == 0:
                print(f"  [{i}/{len(candidates)}] {n_filled} filled, {n_no_match} no-match")
            continue

        new_fields = extract_useful_fields(work, book)
        if not new_fields:
            continue

        if "isbn" in new_fields:
            n_isbn_added += 1
        if "ddc" in new_fields:
            n_ddc_added += 1
        if "lcc" in new_fields:
            n_lcc_added += 1
        if "first_published" in new_fields:
            n_year_added += 1
        if "language" in new_fields:
            n_lang_added += 1
        if "pages" in new_fields:
            n_pages_added += 1

        if args.apply:
            additive_merge(book, new_fields)
            save_json(path, book)
        n_filled += 1

        if i % 25 == 0:
            print(f"  [{i}/{len(candidates)}] {n_filled} filled, {n_no_match} no-match")

    print(f"\nDone. {n_filled} of {len(candidates)} got new fields:")
    print(f"  +ISBN:           {n_isbn_added}")
    print(f"  +DDC:            {n_ddc_added}")
    print(f"  +LCC:            {n_lcc_added}")
    print(f"  +first_published:{n_year_added}")
    print(f"  +language:       {n_lang_added}")
    print(f"  +pages:          {n_pages_added}")
    print(f"  no match on OL:  {n_no_match}")
    if not args.apply:
        print("\nDry-run — pass --apply to write")

    return 0


if __name__ == "__main__":
    sys.exit(main())
