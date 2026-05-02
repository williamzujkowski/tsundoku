#!/usr/bin/env python3
"""Description enrichment — consolidated last-resort fallback.

Replaces the older enrich-descriptions-fallback.py + enrich-descriptions-
lastmile.py. Tries the following sources in order, returning the first
one that produces a substantial description (>30 chars after cleanup):

1. Open Library WORK API — `/works/{key}.json` description field.
   Most authoritative source: work-level summary curated by editors.

2. Open Library EDITIONS API — `/works/{key}/editions.json[].description`.
   Often populated when the work-level field is empty.

3. Google Books by ISBN — precise lookup, modern books only.
   Description is sometimes marketing copy, but always relevant.

4. Open Library search.json `first_sentence` — opening line of the book.
   Niche, but evocative when present.

5. Gutenberg full-text first paragraphs — for public-domain books that
   have a `gutenberg_id`. Last resort, often noisy (boilerplate, chapter
   headings) but parseable for narrative books.

All descriptions are normalized: HTML stripped, truncated at the nearest
sentence boundary near 500 chars.

Usage:
  python scripts/enrich-descriptions.py             # dry-run report
  python scripts/enrich-descriptions.py --apply
  python scripts/enrich-descriptions.py --apply --limit 200
"""

import json
import re
from html.parser import HTMLParser
from urllib.request import urlopen, Request

from enrichment_base import EnrichmentScript
from enrichment_config import USER_AGENT


_MAX_DESC_CHARS = 500
_MIN_DESC_CHARS = 30
_REQUEST_TIMEOUT = 20


class _ParagraphExtractor(HTMLParser):
    """Pull substantial <p> blocks out of HTML, body-only."""

    def __init__(self) -> None:
        super().__init__()
        self._paragraphs: list[str] = []
        self._current = ""
        self._in_p = False
        self._in_body = False

    def handle_starttag(self, tag, attrs):
        if tag == "body":
            self._in_body = True
        if tag == "p" and self._in_body:
            self._in_p = True
            self._current = ""

    def handle_endtag(self, tag):
        if tag == "p" and self._in_p:
            self._in_p = False
            text = self._current.strip()
            if len(text) > 50 and not text.startswith("***"):
                self._paragraphs.append(text)

    def handle_data(self, data):
        if self._in_p:
            self._current += data

    @property
    def paragraphs(self) -> list[str]:
        return self._paragraphs


def _truncate(text: str) -> str:
    """Strip HTML, then trim to the nearest sentence boundary near _MAX_DESC_CHARS."""
    text = re.sub(r"<[^>]+>", "", text).strip()
    if len(text) <= _MAX_DESC_CHARS:
        return text
    cut = text[:_MAX_DESC_CHARS].rfind(". ")
    return text[: cut + 1] if cut > 200 else text[:_MAX_DESC_CHARS]


def _clean_ol_description(raw) -> str | None:
    """OL describes as either a string or {'value': str}; normalise."""
    if isinstance(raw, dict):
        raw = raw.get("value", "")
    if not isinstance(raw, str) or len(raw) < _MIN_DESC_CHARS:
        return None
    return _truncate(raw)


def _fetch_json(url: str) -> dict | None:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=_REQUEST_TIMEOUT) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


class DescriptionsEnricher(EnrichmentScript):
    source_name = "descriptions"
    enrichment_field = "description"

    def search(self, book: dict) -> dict | None:
        # Strategy 1 + 2: Open Library work + editions
        ol_url = book.get("open_library_url") or ""
        if ol_url:
            m = re.search(r"/works/(OL\w+)", ol_url)
            if m:
                work_key = m.group(1)
                desc = self._ol_work(work_key) or self._ol_editions(work_key)
                if desc:
                    return {"description": desc}

        # Strategy 3: Google Books by ISBN
        isbn = book.get("isbn")
        if isbn:
            desc = self._google_books(isbn)
            if desc:
                return {"description": desc}

        # Strategy 4: OL first_sentence search
        title = book.get("title")
        author = book.get("author")
        if title and author:
            desc = self._ol_first_sentence(title, author)
            if desc:
                return {"description": desc}

        # Strategy 5: Gutenberg full-text (public-domain only)
        gid = book.get("gutenberg_id")
        if gid:
            desc = self._gutenberg_text(gid)
            if desc:
                return {"description": desc}

        return None

    def _ol_work(self, work_key: str) -> str | None:
        data = _fetch_json(f"https://openlibrary.org/works/{work_key}.json")
        if not data:
            return None
        return _clean_ol_description(data.get("description"))

    def _ol_editions(self, work_key: str) -> str | None:
        data = _fetch_json(
            f"https://openlibrary.org/works/{work_key}/editions.json?limit=5"
        )
        if not data:
            return None
        for ed in data.get("entries", []) or []:
            desc = _clean_ol_description(ed.get("description"))
            if desc:
                return desc
        return None

    def _ol_first_sentence(self, title: str, author: str) -> str | None:
        from urllib.parse import quote_plus

        url = (
            f"https://openlibrary.org/search.json"
            f"?q={quote_plus(f'{title} {author}')}"
            f"&fields=first_sentence,key&limit=3"
        )
        data = _fetch_json(url)
        if not data:
            return None
        for doc in (data.get("docs") or [])[:3]:
            sentences = doc.get("first_sentence") or []
            if sentences and len(sentences[0]) > _MIN_DESC_CHARS:
                return _truncate(sentences[0])
        return None

    def _google_books(self, isbn: str) -> str | None:
        url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}&maxResults=1"
        data = _fetch_json(url)
        if not data:
            return None
        items = data.get("items") or []
        if not items:
            return None
        desc = (items[0].get("volumeInfo") or {}).get("description") or ""
        if len(desc) < _MIN_DESC_CHARS:
            return None
        return _truncate(desc)

    def _gutenberg_text(self, gid: int) -> str | None:
        url = f"https://www.gutenberg.org/cache/epub/{gid}/pg{gid}-images.html"
        req = Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urlopen(req, timeout=_REQUEST_TIMEOUT) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
        except Exception:
            return None

        parser = _ParagraphExtractor()
        parser.feed(html)

        # Skip Gutenberg-boilerplate paragraphs.
        SKIP_TOKENS = (
            "project gutenberg", "ebook", "copyright", "table of contents",
            "chapter", "preface", "transcriber", "produced by",
            "updated editions",
        )
        good = [
            p for p in parser.paragraphs
            if not any(s in p.lower() for s in SKIP_TOKENS)
        ]
        if not good:
            return None
        return _truncate(" ".join(good[:2]))


if __name__ == "__main__":
    DescriptionsEnricher.cli()
