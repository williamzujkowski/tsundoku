"""Pluggable enrichment sources for book-level gap-filling.

Mirrors author_sources.py: each `from_*` helper takes minimal identifying
info (qid, work key, ISBN, title) and returns a dict of fields ready for
additive_merge / provenance_merge into a book JSON record. Functions
return {} on miss / network error — never raise.

All HTTP goes through `http_cache.cached_fetch` (#91) so re-runs are cheap.
"""

import sys
from pathlib import Path
from typing import Optional
from urllib.parse import quote, quote_plus

sys.path.insert(0, str(Path(__file__).parent))

from http_cache import cached_fetch
from http_retry import fetch_json as _fetch_json  # noqa: F401 — re-exported for tests


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

# Source priority — earlier wins in tie-breaking (richer / more authoritative)
_COVER_PRIORITY = (
    "wikidata_book_v1",
    "wikipedia_book_v1",
    "ol_editions_v1",
    "google_books_v1",
)


def cover_via_chain(book: dict) -> tuple[dict, Optional[str]]:
    """Fire all available cover sources concurrently through their per-source
    rate buckets, then return the highest-priority non-empty result.

    Returns (fields_to_merge, source_label). Empty dict + None on total miss.
    Caller is responsible for additive_merge + provenance tagging.
    """
    # Lazy import — keeps the module loadable for callers that test the
    # source helpers in isolation without pulling in the parallel infra.
    from parallel_fetch import DEFAULT_BUCKETS, parallel_sources

    qid = book.get("wikidata_qid")
    title = book.get("title") or ""
    work_key = book.get("ol_work_key") or book.get("representative_work_key")
    isbn = book.get("isbn")
    author = book.get("author") or ""

    sources: list[tuple[str, callable]] = []
    if qid:
        sources.append(("wikidata", lambda: from_wikidata_book(qid=qid)))
    if title:
        sources.append(("wikipedia", lambda: from_wikipedia_book(title=title)))
    if work_key:
        sources.append(("open_library_editions",
                        lambda: from_open_library_editions(work_key=work_key)))
    if isbn or (title and author):
        sources.append(("google_books",
                        lambda: from_google_books(isbn=isbn, title=title, author=author)))

    if not sources:
        return {}, None

    results = parallel_sources(sources, buckets=DEFAULT_BUCKETS)

    # Walk priority order, return first non-empty result
    src_to_label = {
        "wikidata": "wikidata_book_v1",
        "wikipedia": "wikipedia_book_v1",
        "open_library_editions": "ol_editions_v1",
        "google_books": "google_books_v1",
    }
    for label in _COVER_PRIORITY:
        for src, lab in src_to_label.items():
            if lab == label and results.get(src):
                return results[src], label

    return {}, None
