#!/usr/bin/env python3
"""
Enrich author data via the shared author_sources module.

Usage:
  python scripts/enrich-authors.py                # enrich all authors
  python scripts/enrich-authors.py --limit 100    # enrich top 100 authors (most books first)

Routes through the same Wikipedia / Open Library / Wikidata sources
that enrich-authors-gaps.py uses, so the create-new and fill-gaps
flows stay in lockstep when sources change shape upstream.
"""

import json
import re
import sys
import time
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from author_sources import (
    from_open_library_author_page,
    from_wikidata,
    from_wikipedia,
)
from json_merge import additive_merge, load_existing, save_json

BOOKS_DIR = Path(__file__).parent.parent / "src" / "content" / "books"
AUTHORS_DIR = Path(__file__).parent.parent / "src" / "content" / "authors"
RATE_LIMIT_SECONDS = 1.0


def slugify(name: str) -> str:
    """Convert author name to URL-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug


def get_all_authors() -> list[dict]:
    """Collect unique authors from book JSON files, sorted by book count descending."""
    author_counts: dict[str, int] = {}

    for book_file in BOOKS_DIR.glob("*.json"):
        try:
            with open(book_file, "r", encoding="utf-8") as f:
                book = json.load(f)
            author = book.get("author", "").strip()
            if author:
                author_counts[author] = author_counts.get(author, 0) + 1
        except (json.JSONDecodeError, IOError) as e:
            print(f"  Warning: could not read {book_file.name}: {e}")

    # Sort by book count descending, then alphabetically
    authors = [
        {"name": name, "book_count": count}
        for name, count in sorted(
            author_counts.items(), key=lambda x: (-x[1], x[0])
        )
    ]
    return authors


def enrich_author(name: str, book_count: int) -> dict:
    """Enrich a single author by walking the shared source chain.

    Wikipedia → Open Library author page → Wikidata. Wikipedia wins for
    bio + photo + canonical URL. OL contributes structured birth/death
    dates when Wikipedia's regex didn't get them. Wikidata is the
    last-mile fallback when the first two miss outright.
    """
    slug = slugify(name)
    author_data = {
        "name": name,
        "slug": slug,
        "book_count": book_count,
    }

    print("  Fetching Wikipedia...")
    wiki = from_wikipedia(name=name)
    time.sleep(RATE_LIMIT_SECONDS)

    print("  Fetching Open Library...")
    ol = from_open_library_author_page(name=name)
    time.sleep(RATE_LIMIT_SECONDS)

    wikidata: dict = {}
    if not (wiki or ol):
        print("  Falling back to Wikidata...")
        wikidata = from_wikidata(name=name)
        time.sleep(RATE_LIMIT_SECONDS)

    # Wikipedia first for narrative fields
    for field in ("bio", "photo_url", "wikipedia_url"):
        for src_dict in (wiki, ol, wikidata):
            if src_dict.get(field):
                author_data[field] = src_dict[field]
                break

    # OL structured dates win, with Wikipedia/Wikidata as fallbacks
    for field in ("birth_year", "death_year"):
        for src_dict in (ol, wiki, wikidata):
            if src_dict.get(field):
                author_data[field] = src_dict[field]
                break

    if ol.get("open_library_url"):
        author_data["open_library_url"] = ol["open_library_url"]

    return author_data


def main():
    parser = argparse.ArgumentParser(description="Enrich author data from APIs")
    parser.add_argument(
        "--limit", type=int, default=0, help="Max number of authors to process (0=all)"
    )
    parser.add_argument(
        "--refresh-existing",
        action="store_true",
        help="Re-fetch authors that already have a JSON file (additive merge — no field is ever wiped). "
             "Without this flag, existing files are skipped for speed.",
    )
    args = parser.parse_args()

    AUTHORS_DIR.mkdir(parents=True, exist_ok=True)

    authors = get_all_authors()
    print(f"Found {len(authors)} unique authors in book collection.")

    if args.limit > 0:
        authors = authors[: args.limit]
        print(f"Processing top {len(authors)} authors (most books first).")

    enriched_new = 0
    enriched_updated = 0
    skipped = 0
    failed = 0
    no_change = 0

    for i, author_info in enumerate(authors):
        name = author_info["name"]
        slug = slugify(name)
        output_file = AUTHORS_DIR / f"{slug}.json"
        already_exists = output_file.exists()

        if already_exists and not args.refresh_existing:
            skipped += 1
            continue

        print(f"\n[{i + 1}/{len(authors)}] {name} ({author_info['book_count']} books)")

        try:
            new_data = enrich_author(name, author_info["book_count"])
            existing = load_existing(output_file)
            # book_count comes from the book corpus, not the API — keep it fresh.
            if "book_count" in new_data:
                existing["book_count"] = new_data["book_count"]
            # name and slug are identity, not enriched fields — set if missing.
            for k in ("name", "slug"):
                if k in new_data and not existing.get(k):
                    existing[k] = new_data[k]
            changed = additive_merge(existing, new_data)
            if changed or not already_exists:
                save_json(output_file, existing)
                if already_exists:
                    enriched_updated += 1
                else:
                    enriched_new += 1
                fields = [k for k in ("bio", "photo_url", "wikipedia_url", "open_library_url", "birth_year") if k in existing]
                print(f"  Saved: {output_file.name} ({', '.join(fields) if fields else 'basic only'})")
            else:
                no_change += 1
                print("  No new fields — existing record unchanged.")

        except Exception as e:
            print(f"  FAILED: {e}")
            failed += 1

    print(
        f"\nDone: {enriched_new} new, {enriched_updated} updated additively, "
        f"{no_change} no-change, {skipped} skipped (existing), {failed} failed."
    )


if __name__ == "__main__":
    main()
