"""Pluggable enrichment sources for book-level gap-filling.

Mirrors author_sources.py: each `from_*` helper takes minimal identifying
info (qid, work key, ISBN, title) and returns a dict of fields ready for
additive_merge / provenance_merge into a book JSON record. Functions
return {} on miss / network error — never raise.

All HTTP goes through `http_cache.cached_fetch` (#91) so re-runs are cheap.
"""

import json
import re
import sys
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote, quote_plus
from urllib.request import urlopen, Request

sys.path.insert(0, str(Path(__file__).parent))

from enrichment_config import USER_AGENT
from http_cache import cached_fetch


HTTP_TIMEOUT = 20


def _fetch_json(url: str) -> Optional[dict]:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return json.loads(resp.read())
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------------------
# Wikidata (P18 cover image — last-mile fallback for famous works)
# ---------------------------------------------------------------------------

def from_wikidata_book(*, qid: str) -> dict:
    """Pull the P18 image (cover) for a book entity by QID."""
    if not qid:
        return {}
    url = f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
    data = cached_fetch("wikidata_entity", qid, lambda: _fetch_json(url), url=url)
    if not data:
        return {}
    claims = ((data.get("entities") or {}).get(qid) or {}).get("claims") or {}
    for stmt in claims.get("P18") or []:
        try:
            filename = stmt["mainsnak"]["datavalue"]["value"]
        except (KeyError, TypeError):
            continue
        if filename:
            return {
                "cover_url": (
                    f"https://commons.wikimedia.org/wiki/Special:FilePath/{quote(filename)}?width=600"
                ),
            }
    return {}


# ---------------------------------------------------------------------------
# Wikipedia REST summary — originalimage often is the cover for famous works
# ---------------------------------------------------------------------------

def from_wikipedia_book(*, title: str) -> dict:
    """Wikipedia's per-book article often uses the cover as its lead image."""
    if not title:
        return {}
    encoded = quote(title.replace(" ", "_"), safe="")
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
    data = cached_fetch("wikipedia", f"book:{title}", lambda: _fetch_json(url), url=url)
    if not data or data.get("type") == "disambiguation":
        return {}
    img = (data.get("originalimage") or {}).get("source") \
        or (data.get("thumbnail") or {}).get("source")
    if img and "wiki" in img.lower():
        return {"cover_url": img}
    return {}


# ---------------------------------------------------------------------------
# Open Library editions — walk editions[] for one with a non-empty covers[]
# ---------------------------------------------------------------------------

def from_open_library_editions(*, work_key: str) -> dict:
    """Walk editions for an OL work and return covers from the first edition with one."""
    if not work_key:
        return {}
    if not work_key.startswith("/works/"):
        work_key = f"/works/{work_key}"
    url = f"https://openlibrary.org{work_key}/editions.json?limit=20"
    data = cached_fetch("open_library_editions", work_key, lambda: _fetch_json(url), url=url)
    if not data:
        return {}
    for ed in data.get("entries", []) or []:
        valid = [c for c in (ed.get("covers") or []) if isinstance(c, int) and c > 0]
        if valid:
            cid = valid[0]
            return {
                "cover_url": f"https://covers.openlibrary.org/b/id/{cid}-M.jpg",
                "cover_url_large": f"https://covers.openlibrary.org/b/id/{cid}-L.jpg",
            }
    return {}


# ---------------------------------------------------------------------------
# Google Books — volumeInfo.imageLinks (large > medium > thumbnail)
# ---------------------------------------------------------------------------

_GB_IMG_KEYS = ("large", "medium", "thumbnail", "smallThumbnail")


def from_google_books(*, isbn: Optional[str] = None, title: Optional[str] = None,
                      author: Optional[str] = None) -> dict:
    """Pull the best available cover image from Google Books volumes."""
    if isbn:
        query = f"isbn:{quote_plus(isbn)}"
        cache_key = f"isbn:{isbn}"
    elif title and author:
        query = f"intitle:{quote_plus(title)}+inauthor:{quote_plus(author)}"
        cache_key = f"ti:{title[:80]}|au:{author[:60]}"
    else:
        return {}
    url = f"https://www.googleapis.com/books/v1/volumes?q={query}&maxResults=1"
    data = cached_fetch("google_books", cache_key, lambda: _fetch_json(url), url=url)
    if not data:
        return {}
    items = data.get("items") or []
    if not items:
        return {}
    images = (items[0].get("volumeInfo") or {}).get("imageLinks") or {}
    for k in _GB_IMG_KEYS:
        if images.get(k):
            return {"cover_url": images[k].replace("http://", "https://")}
    return {}


# ---------------------------------------------------------------------------
# Multi-source orchestrator (used by enrich-gaps.py)
# ---------------------------------------------------------------------------

def cover_via_chain(book: dict) -> tuple[dict, Optional[str]]:
    """Walk the full source priority chain for a missing cover.

    Returns (fields_to_merge, source_label). Empty dict + None on total miss.
    Caller is responsible for additive_merge + provenance tagging.
    """
    qid = book.get("wikidata_qid")
    if qid:
        new = from_wikidata_book(qid=qid)
        if new:
            return new, "wikidata_book_v1"

    title = book.get("title") or ""
    if title:
        new = from_wikipedia_book(title=title)
        if new:
            return new, "wikipedia_book_v1"

    work_key = book.get("ol_work_key") or book.get("representative_work_key")
    if work_key:
        new = from_open_library_editions(work_key=work_key)
        if new:
            return new, "ol_editions_v1"

    isbn = book.get("isbn")
    author = book.get("author") or ""
    new = from_google_books(isbn=isbn, title=title, author=author)
    if new:
        return new, "google_books_v1"

    return {}, None
