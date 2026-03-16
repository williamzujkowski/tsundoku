"""
Centralized configuration and shared utilities for all enrichment scripts.

Single source of truth for rate limits, API URLs, timeouts, user agent,
and common book-loading patterns.
"""

import json
from pathlib import Path

# Directories
BOOKS_DIR = Path(__file__).parent.parent / "src" / "content" / "books"
AUTHORS_DIR = Path(__file__).parent.parent / "src" / "content" / "authors"
DATA_DIR = Path(__file__).parent.parent / "data"
ERROR_LOG = DATA_DIR / "enrichment-errors.jsonl"

# HTTP
USER_AGENT = "Tsundoku/1.0 (https://github.com/williamzujkowski/tsundoku)"
DEFAULT_TIMEOUT = 15  # seconds

# Rate limits per source (seconds between requests)
RATE_LIMITS = {
    "open_library": 1.0,
    "google_books": 1.0,
    "gutenberg": 0.5,
    "librivox": 1.0,
    "hathitrust": 0.5,
    "wikipedia": 1.0,
}

def load_all_books() -> list[tuple[Path, dict]]:
    """Load all book JSON files sorted by path."""
    return [
        (bp, json.loads(bp.read_text()))
        for bp in sorted(BOOKS_DIR.glob("*.json"))
    ]


def save_book(path: Path, book: dict) -> None:
    """Write book JSON with consistent formatting."""
    path.write_text(json.dumps(book, indent=2, ensure_ascii=False))


# API base URLs
API_URLS = {
    "open_library_search": "https://openlibrary.org/search.json",
    "google_books": "https://www.googleapis.com/books/v1/volumes",
    "gutenberg": "https://gutendex.com/books/",
    "librivox": "https://librivox.org/api/feed/audiobooks",
    "hathitrust": "https://catalog.hathitrust.org/api/volumes/brief",
    "wikipedia": "https://en.wikipedia.org/api/rest_v1/page/summary",
}
