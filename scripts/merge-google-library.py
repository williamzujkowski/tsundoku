#!/usr/bin/env python3
"""
Merge Google Play Books library into tsundoku collection.

Reads data/dirtylist.csv, cleans titles, deduplicates against existing
books, looks up authors via Google Books API, categorizes, filters
low-quality entries, and outputs new book JSON files.

Usage:
  python scripts/merge-google-library.py                # full run
  python scripts/merge-google-library.py --dry-run      # preview only
  python scripts/merge-google-library.py --limit 50     # process first 50
"""

import csv
import json
import re
import sys
import time
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import quote_plus

BOOKS_DIR = Path(__file__).parent.parent / "src" / "content" / "books"
DIRTY_CSV = Path(__file__).parent.parent / "data" / "dirtylist.csv"
REPORT_PATH = Path(__file__).parent.parent / "data" / "merge-report.json"
UA = "Tsundoku/1.0 (https://github.com/williamzujkowski/tsundoku)"

# ── Filters ──────────────────────────────────────────────────────────

# Tech tutorial keywords that indicate low-quality/tutorial content
FILTER_KEYWORDS = [
    "for dummies", "cookbook", "crash course", "bootcamp", "certification",
    "exam guide", "comptia", "hands-on", "tutorial", "step-by-step guide",
    "in action", "in practice", "learning ", "mastering ", "beginning ",
    "professional ", "getting started with", "up and running",
    # Specific tech
    "aws ", "azure ", "google cloud", "gcp ", "docker ", "kubernetes ",
    "jenkins ", "terraform ", "ansible ", "puppet ", "chef ",
    "mongodb ", "mysql ", "postgresql ", "redis ",
    "react ", "angular ", "vue.js", "node.js", "express.js",
    "spring boot", "django ", "flask ", "rails ",
    "xamarin", "flutter ", "unity ", "unreal engine",
    "devops", "microservices", "serverless", "blockchain",
    "full stack", "front-end", "back-end",
    "linux admin", "windows server", "cisco ", "vmware ",
    "web development", "mobile development", "game development",
    "machine learning with", "deep learning with",
    # Kids/juvenile
    "sesame street", "coloring book", "activity book", "sticker book",
    # Academic papers/reports
    "unifying review", "technical report", "proceedings of",
    "a survey of", "lecture notes",
    # Low-quality misc
    "for beginners", "quick start", "cheat sheet", "pocket guide",
    "reference manual", "user guide", "admin guide",
]

# Categories for automatic classification
CATEGORY_PATTERNS = {
    "Science Fiction": ["sci-fi", "science fiction", "space opera", "cyberpunk", "dystopia"],
    "Fantasy": ["fantasy", "magic", "dragon", "sword", "quest", "fairy tale"],
    "Horror": ["horror", "gothic", "supernatural", "ghost", "dark fiction"],
    "Mystery": ["mystery", "detective", "crime", "thriller", "whodunit"],
    "Literature": [],  # Default for fiction
    "Philosophy": ["philosophy", "philosophical", "ethics", "metaphysics"],
    "History": ["history", "historical", "ancient", "medieval", "war"],
    "Science": ["science", "physics", "chemistry", "biology", "astronomy"],
    "Poetry": ["poems", "poetry", "verse", "sonnets"],
    "Drama": ["play", "drama", "theatre", "tragedy", "comedy"],
    "Classics": [],  # For pre-1900 works
    "Security": ["security", "hacking", "cryptography", "cyber", "malware"],
    "Computer Science": ["algorithm", "programming", "software", "computer", "computing"],
    "Economics": ["economics", "economy", "capitalism", "market"],
    "Mathematics": ["mathematics", "math", "algebra", "geometry", "calculus"],
}


# Matches "Author_Name_-_Title" filename patterns (with optional .epub/.pdf
# extension). Two or more underscore-joined TitleCase tokens before "_-_"
# is the cue that we're looking at an export filename, not a real title.
_FILENAME_AUTHOR_TITLE = re.compile(
    r"^([A-Z][A-Za-z']*(?:_[A-Z][A-Za-z']*)+)_-_(.+?)(?:\.[a-zA-Z0-9]{2,5})?$"
)


def clean_title(title: str) -> str:
    """Normalize a title string."""
    # Fix smart quotes and dashes
    title = title.replace("\u2019", "'").replace("\u2018", "'")
    title = title.replace("\u2014", "—").replace("\u2013", "–")
    title = title.replace("\u201c", '"').replace("\u201d", '"')
    title = title.replace("\u00e9", "é").replace("\u00e8", "è")
    title = title.strip().strip('"').strip()
    # Strip "Author_Name_-_Title.epub" filename pattern
    m = _FILENAME_AUTHOR_TITLE.match(title)
    if m:
        title = m.group(2).replace("_", " ").strip()
    return title


def make_slug(title: str) -> str:
    """Generate a URL-safe slug from a title."""
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug


def is_low_quality(title: str) -> bool:
    """Check if a title matches low-quality filter patterns."""
    tl = title.lower()
    return any(kw in tl for kw in FILTER_KEYWORDS)


def lookup_google_books(title: str) -> dict | None:
    """Look up a book on Google Books API to get author and metadata."""
    query = quote_plus(title)
    url = f"https://www.googleapis.com/books/v1/volumes?q=intitle:{query}&maxResults=1"

    req = Request(url, headers={"User-Agent": UA})
    try:
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            items = data.get("items", [])
            if not items:
                return None
            vol = items[0].get("volumeInfo", {})
            return {
                "author": ", ".join(vol.get("authors", ["Unknown"])),
                "description": (vol.get("description", "") or "")[:500],
                "categories": vol.get("categories", []),
                "published_date": vol.get("publishedDate", ""),
                "page_count": vol.get("pageCount"),
                "isbn": next(
                    (i["identifier"] for i in vol.get("industryIdentifiers", [])
                     if i.get("type") in ("ISBN_13", "ISBN_10")),
                    None
                ),
                "cover_url": (vol.get("imageLinks", {}).get("thumbnail", "") or "").replace("http://", "https://"),
                "google_books_url": vol.get("infoLink"),
            }
    except Exception:
        return None


def classify_category(title: str, metadata: dict | None) -> str:
    """Guess a category based on title and metadata."""
    text = title.lower()
    if metadata:
        cats = metadata.get("categories", [])
        if cats:
            cat = cats[0].lower()
            for category, keywords in CATEGORY_PATTERNS.items():
                if any(kw in cat for kw in keywords):
                    return category
            if "fiction" in cat:
                return "Literature"
            if "history" in cat:
                return "History"

    # Fallback: pattern match on title
    for category, keywords in CATEGORY_PATTERNS.items():
        if any(kw in text for kw in keywords):
            return category

    return "Literature"  # Default


def get_publish_year(metadata: dict | None) -> int | None:
    """Extract publication year from metadata."""
    if not metadata:
        return None
    date_str = metadata.get("published_date", "")
    if date_str and len(date_str) >= 4:
        try:
            return int(date_str[:4])
        except ValueError:
            pass
    return None


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Merge Google Play Books library")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, don't create files")
    parser.add_argument("--limit", type=int, default=0, help="Max titles to process")
    args = parser.parse_args()

    # Load existing books
    existing_titles = set()
    existing_slugs = set()
    for bp in BOOKS_DIR.glob("*.json"):
        d = json.loads(bp.read_text())
        existing_titles.add(d["title"].lower().strip())
        existing_slugs.add(d["slug"])

    # Read and clean dirty list
    with open(DIRTY_CSV, encoding="utf-8") as f:
        raw_lines = f.readlines()

    titles = set()
    for line in raw_lines:
        t = clean_title(line)
        if t and len(t) > 1:
            titles.add(t)

    print(f"Dirty list: {len(raw_lines)} lines → {len(titles)} unique titles")

    # Deduplicate against existing
    new_titles = []
    already_have = 0
    for t in sorted(titles):
        if t.lower().strip() in existing_titles:
            already_have += 1
        else:
            new_titles.append(t)

    print(f"Already in collection: {already_have}")
    print(f"New titles to process: {len(new_titles)}")

    # Filter low quality
    filtered = []
    kept = []
    for t in new_titles:
        if is_low_quality(t):
            filtered.append(t)
        else:
            kept.append(t)

    print(f"Filtered (tech/tutorial): {len(filtered)}")
    print(f"Kept for processing: {len(kept)}")

    if args.limit > 0:
        kept = kept[: args.limit]
        print(f"Limited to: {len(kept)}")

    if args.dry_run:
        print("\n=== DRY RUN — would add these books ===")
        for t in kept[:50]:
            print(f"  {t}")
        if len(kept) > 50:
            print(f"  ... and {len(kept) - 50} more")

        print(f"\n=== FILTERED OUT ===")
        for t in filtered:
            print(f"  ✗ {t}")
        return

    # Process each title: lookup metadata, create JSON
    added = 0
    errors = 0
    report = {"added": [], "filtered": filtered, "errors": [], "skipped": []}

    for i, title in enumerate(kept, 1):
        print(f"[{i}/{len(kept)}] {title}...", end=" ", flush=True)

        # Lookup metadata
        metadata = lookup_google_books(title)
        time.sleep(0.3)  # Rate limit

        if not metadata:
            print("no metadata found")
            report["skipped"].append(title)
            # Still create basic entry
            metadata = {}

        author = metadata.get("author", "Unknown")
        if author == "Unknown":
            print(f"→ {author} (no author found)")
            report["errors"].append({"title": title, "reason": "no author"})

        # Generate slug
        slug = make_slug(title)
        counter = 2
        while slug in existing_slugs:
            slug = f"{make_slug(title)}-{counter}"
            counter += 1
        existing_slugs.add(slug)

        # Classify
        category = classify_category(title, metadata)
        year = get_publish_year(metadata)

        # Build book entry
        book = {
            "title": title,
            "author": author,
            "category": category,
            "priority": 2,  # Default: Recommended
            "slug": slug,
            "tags": ["google-play-library"],
            "reading_status": "read",  # From personal library = likely read
        }

        # Add metadata if available
        if metadata.get("description"):
            book["description"] = metadata["description"]
        if metadata.get("cover_url"):
            book["cover_url"] = metadata["cover_url"]
        if metadata.get("isbn"):
            book["isbn"] = metadata["isbn"]
        if year:
            book["first_published"] = year
        if metadata.get("page_count"):
            book["pages"] = metadata["page_count"]
        if metadata.get("google_books_url"):
            book["google_books_url"] = metadata["google_books_url"]

        book["language"] = "eng"

        # Write JSON file
        book_path = BOOKS_DIR / f"{slug}.json"
        book_path.write_text(json.dumps(book, indent=2, ensure_ascii=False))
        added += 1
        report["added"].append({"title": title, "author": author, "category": category})
        print(f"✓ {author} [{category}]")

    # Save report
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    print(f"\nDone: {added} added, {len(filtered)} filtered, {len(report['errors'])} errors")
    print(f"Report saved to: {REPORT_PATH}")


if __name__ == "__main__":
    main()
