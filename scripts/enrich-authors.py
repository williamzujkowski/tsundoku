#!/usr/bin/env python3
"""
Enrich author data from Wikipedia and Open Library APIs.

Usage:
  python scripts/enrich-authors.py                # enrich all authors
  python scripts/enrich-authors.py --limit 100    # enrich top 100 authors (most books first)

APIs used (free, no keys required):
  Wikipedia: https://en.wikipedia.org/api/rest_v1/page/summary/{name}
  Open Library: https://openlibrary.org/search/authors.json?q={name}
"""

import json
import re
import sys
import time
import argparse
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from urllib.parse import quote

from json_merge import additive_merge, load_existing, save_json
from http_cache import cached_fetch

BOOKS_DIR = Path(__file__).parent.parent / "src" / "content" / "books"
AUTHORS_DIR = Path(__file__).parent.parent / "src" / "content" / "authors"
USER_AGENT = "Tsundoku/1.0 (https://github.com/williamzujkowski/tsundoku)"
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


def fetch_json(url: str) -> dict | None:
    """Fetch JSON from a URL with error handling."""
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except HTTPError as e:
        if e.code == 404:
            return None
        print(f"  HTTP {e.code} for {url}")
        return None
    except (URLError, TimeoutError, json.JSONDecodeError) as e:
        print(f"  Error fetching {url}: {e}")
        return None


def fetch_wikipedia(author_name: str) -> dict:
    """Fetch author info from Wikipedia REST API."""
    result = {}
    # Try the name as-is first, then with underscores
    encoded = quote(author_name.replace(" ", "_"), safe="")
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
    data = cached_fetch("wikipedia", author_name, lambda: fetch_json(url), url=url)

    if not data or data.get("type") == "disambiguation":
        return result

    extract = data.get("extract", "")
    if extract:
        result["bio"] = extract

    thumbnail = data.get("thumbnail", {})
    if thumbnail and thumbnail.get("source"):
        # Get a larger version by replacing size in URL
        photo = thumbnail["source"]
        # Wikipedia thumbnails often have /NNNpx- in URL, try to get larger
        photo = re.sub(r"/\d+px-", "/400px-", photo)
        result["photo_url"] = photo

    content_urls = data.get("content_urls", {})
    desktop = content_urls.get("desktop", {})
    if desktop.get("page"):
        result["wikipedia_url"] = desktop["page"]

    # Try to extract birth/death years from description
    desc = data.get("description", "")
    extract_text = data.get("extract", "")

    # Look for year patterns like (1564-1616) or (born 1947)
    year_pattern = r"\((\d{4})\s*[-–]\s*(\d{4})\)"
    match = re.search(year_pattern, extract_text)
    if match:
        result["birth_year"] = int(match.group(1))
        result["death_year"] = int(match.group(2))
    else:
        born_pattern = r"\(born\s+.*?(\d{4})\)"
        match = re.search(born_pattern, extract_text, re.IGNORECASE)
        if match:
            result["birth_year"] = int(match.group(1))

    # Also check description for years
    if "birth_year" not in result:
        match = re.search(year_pattern, desc)
        if match:
            result["birth_year"] = int(match.group(1))
            result["death_year"] = int(match.group(2))

    return result


def fetch_open_library(author_name: str) -> dict:
    """Fetch author info from Open Library Authors API."""
    result = {}
    encoded = quote(author_name, safe="")
    url = f"https://openlibrary.org/search/authors.json?q={encoded}"
    data = cached_fetch("open_library", author_name, lambda: fetch_json(url), url=url)

    if not data or not data.get("docs"):
        return result

    # Take the first (best match) result
    author = data["docs"][0]
    author_key = author.get("key", "")

    if author_key:
        result["open_library_url"] = f"https://openlibrary.org/authors/{author_key}"

        # Open Library author photos
        # https://covers.openlibrary.org/a/olid/{OLID}-M.jpg
        result["open_library_photo_url"] = (
            f"https://covers.openlibrary.org/a/olid/{author_key}-M.jpg"
        )

    birth = author.get("birth_date", "")
    death = author.get("death_date", "")

    if birth:
        year_match = re.search(r"\d{4}", birth)
        if year_match:
            result["birth_year"] = int(year_match.group())

    if death:
        year_match = re.search(r"\d{4}", death)
        if year_match:
            result["death_year"] = int(year_match.group())

    return result


def enrich_author(name: str, book_count: int) -> dict:
    """Enrich a single author with data from multiple APIs."""
    slug = slugify(name)
    author_data = {
        "name": name,
        "slug": slug,
        "book_count": book_count,
    }

    # Fetch from Wikipedia
    print(f"  Fetching Wikipedia...")
    wiki = fetch_wikipedia(name)
    time.sleep(RATE_LIMIT_SECONDS)

    # Fetch from Open Library
    print(f"  Fetching Open Library...")
    ol = fetch_open_library(name)
    time.sleep(RATE_LIMIT_SECONDS)

    # Merge data — Wikipedia takes priority for bio and photo
    if wiki.get("bio"):
        author_data["bio"] = wiki["bio"]

    # Prefer Wikipedia photo, fall back to Open Library
    if wiki.get("photo_url"):
        author_data["photo_url"] = wiki["photo_url"]
    elif ol.get("open_library_photo_url"):
        author_data["photo_url"] = ol["open_library_photo_url"]

    if wiki.get("wikipedia_url"):
        author_data["wikipedia_url"] = wiki["wikipedia_url"]

    if ol.get("open_library_url"):
        author_data["open_library_url"] = ol["open_library_url"]

    # Prefer Open Library birth/death years (more structured), fall back to Wikipedia
    if ol.get("birth_year"):
        author_data["birth_year"] = ol["birth_year"]
    elif wiki.get("birth_year"):
        author_data["birth_year"] = wiki["birth_year"]

    if ol.get("death_year"):
        author_data["death_year"] = ol["death_year"]
    elif wiki.get("death_year"):
        author_data["death_year"] = wiki["death_year"]

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
