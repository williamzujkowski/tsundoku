#!/usr/bin/env python3
"""
Generate stats.json from book data for the tsundoku site.

Produces a comprehensive statistics file that pages can import
for accurate, auto-generated counts. Run as part of the build
pipeline or manually after data changes.

Usage:
  python scripts/generate-stats.py
"""

import json
from collections import Counter
from pathlib import Path

BOOKS_DIR = Path(__file__).parent.parent / "src" / "content" / "books"
AUTHORS_DIR = Path(__file__).parent.parent / "src" / "content" / "authors"
STATS_PATH = Path(__file__).parent.parent / "src" / "data" / "stats.json"


def generate_stats() -> dict:
    """Generate comprehensive statistics from book + author data."""
    books = []
    for bp in sorted(BOOKS_DIR.glob("*.json")):
        books.append(json.loads(bp.read_text()))
    authors_data = []
    for ap in sorted(AUTHORS_DIR.glob("*.json")):
        authors_data.append(json.loads(ap.read_text()))

    # Basic counts
    total = len(books)
    categories = Counter(b["category"] for b in books)
    authors = Counter(b["author"] for b in books)
    priorities = Counter(b["priority"] for b in books)

    # Enrichment coverage
    has_cover = sum(1 for b in books if b.get("cover_url"))
    has_desc = sum(1 for b in books if b.get("description"))
    has_isbn = sum(1 for b in books if b.get("isbn"))
    has_pages = sum(1 for b in books if b.get("pages"))
    has_year = sum(1 for b in books if b.get("first_published"))
    has_subject_facet = sum(1 for b in books if b.get("subject_facet"))
    has_ddc = sum(1 for b in books if b.get("ddc"))
    has_lcc = sum(1 for b in books if b.get("lcc"))
    has_wikidata = sum(1 for b in books if b.get("wikidata_qid"))
    has_orig_lang = sum(1 for b in books if b.get("original_language"))
    has_orig_pub = sum(1 for b in books if b.get("original_publisher"))
    has_awards_book = sum(1 for b in books if b.get("awards"))
    has_series = sum(1 for b in books if b.get("series"))

    # Top authors by book count
    top_authors = [
        {"name": name, "count": count}
        for name, count in authors.most_common(20)
    ]

    # Categories sorted by count
    category_stats = sorted(
        [{"name": name, "count": count} for name, count in categories.items()],
        key=lambda x: -x["count"],
    )

    # Author-level Wikidata enrichment
    has_nationality = sum(1 for a in authors_data if a.get("nationality"))
    has_alt_names = sum(1 for a in authors_data if a.get("alternate_names"))
    has_movements = sum(1 for a in authors_data if a.get("movements"))
    has_awards_author = sum(1 for a in authors_data if a.get("awards"))
    has_viaf = sum(1 for a in authors_data if a.get("viaf_id"))
    has_wd_author = sum(1 for a in authors_data if a.get("wikidata_qid"))

    # Nationality distribution (top 12). Books inherit from their authors,
    # which is more meaningful than counting authors-with-nationality.
    author_nationality = {}
    for a in authors_data:
        nats = a.get("nationality") or []
        if nats:
            # Primary nationality only (first listed)
            author_nationality[a["name"]] = nats[0]
    book_nationality = Counter()
    for b in books:
        nat = author_nationality.get(b["author"])
        if nat:
            book_nationality[nat] += 1
    nationality_distribution = [
        {"code": code, "count": count}
        for code, count in book_nationality.most_common(12)
    ]

    # Year distribution — coarse buckets
    years = [b["first_published"] for b in books if b.get("first_published")]
    year_ranges = {
        "before_1800": sum(1 for y in years if y < 1800),
        "1800_1899": sum(1 for y in years if 1800 <= y < 1900),
        "1900_1949": sum(1 for y in years if 1900 <= y < 1950),
        "1950_1999": sum(1 for y in years if 1950 <= y < 2000),
        "2000_plus": sum(1 for y in years if y >= 2000),
    }

    # Decade timeline — for the visualization we want every decade with a count
    decade_counts: Counter = Counter()
    for y in years:
        if y is None:
            continue
        decade = (y // 10) * 10  # 1949 → 1940
        decade_counts[decade] += 1
    timeline = [{"decade": d, "count": decade_counts[d]} for d in sorted(decade_counts)]

    # Oldest and newest
    oldest = min(years) if years else None
    newest = max(years) if years else None

    # Fun bookshelf metrics
    page_counts = [b["pages"] for b in books if b.get("pages")]
    total_pages = sum(page_counts)
    # Average reading speed: 250 words per page, 250 words per minute
    estimated_reading_hours = round(total_pages * 250 / 250 / 60)
    # Average book spine: ~2.5cm
    shelf_meters = round(total * 0.025, 1)

    # Free reading/listening links
    has_gutenberg = sum(1 for b in books if b.get("gutenberg_url"))
    has_librivox = sum(1 for b in books if b.get("librivox_url"))
    has_hathitrust = sum(1 for b in books if b.get("hathitrust_url"))
    has_worldcat = sum(1 for b in books if b.get("worldcat_url"))

    # Reading status
    reading_statuses = Counter(b.get("reading_status", "") for b in books)
    read_count = reading_statuses.get("read", 0)
    reading_count = reading_statuses.get("reading", 0)
    want_count = reading_statuses.get("want", 0)

    stats = {
        "total_books": total,
        "total_categories": len(categories),
        "total_authors": len(authors),
        "priorities": {
            "must_read": priorities.get(1, 0),
            "recommended": priorities.get(2, 0),
            "supplementary": priorities.get(3, 0),
        },
        "enrichment": {
            "covers": has_cover,
            "covers_pct": round(100 * has_cover / total, 1),
            "descriptions": has_desc,
            "descriptions_pct": round(100 * has_desc / total, 1),
            "isbns": has_isbn,
            "isbns_pct": round(100 * has_isbn / total, 1),
            "pages": has_pages,
            "pages_pct": round(100 * has_pages / total, 1),
            "years": has_year,
            "subject_facet": has_subject_facet,
            "ddc": has_ddc,
            "lcc": has_lcc,
            "wikidata": has_wikidata,
            "original_language": has_orig_lang,
            "original_publisher": has_orig_pub,
            "awards": has_awards_book,
            "series": has_series,
        },
        "author_enrichment": {
            "total_authors": len(authors_data),
            "wikidata": has_wd_author,
            "nationality": has_nationality,
            "alternate_names": has_alt_names,
            "movements": has_movements,
            "awards": has_awards_author,
            "viaf": has_viaf,
        },
        "nationality_distribution": nationality_distribution,
        "timeline": timeline,
        "top_authors": top_authors,
        "categories": category_stats,
        "year_distribution": year_ranges,
        "reading_progress": {
            "read": read_count,
            "reading": reading_count,
            "want": want_count,
            "unread": total - read_count - reading_count - want_count,
        },
        "links": {
            "gutenberg": has_gutenberg,
            "librivox": has_librivox,
            "hathitrust": has_hathitrust,
            "worldcat": has_worldcat,
        },
        "oldest_year": oldest,
        "newest_year": newest,
        "bookshelf": {
            "total_pages": total_pages,
            "estimated_reading_hours": estimated_reading_hours,
            "shelf_meters": shelf_meters,
            "books_with_pages": len(page_counts),
        },
        "generated_at": __import__("datetime").datetime.now().isoformat(),
    }

    return stats


def main() -> None:
    stats = generate_stats()

    STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATS_PATH.write_text(json.dumps(stats, indent=2, ensure_ascii=False))

    print(f"Stats generated: {STATS_PATH}")
    print(f"  Books: {stats['total_books']}")
    print(f"  Categories: {stats['total_categories']}")
    print(f"  Authors: {stats['total_authors']}")
    print(f"  Covers: {stats['enrichment']['covers_pct']}%")
    print(f"  Descriptions: {stats['enrichment']['descriptions_pct']}%")
    print(f"  ISBNs: {stats['enrichment']['isbns_pct']}%")
    print(f"  Year range: {stats['oldest_year']} — {stats['newest_year']}")


if __name__ == "__main__":
    main()
