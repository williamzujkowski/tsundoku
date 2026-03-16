#!/usr/bin/env python3
"""
Last-mile description enrichment using three fallback strategies:

1. Gutenberg full-text first paragraph (for books with gutenberg_id)
2. Open Library editions API (deeper than works API)
3. Google Books ISBN lookup (precise match)

Only processes books that still lack descriptions after all other enrichers.

Usage:
  python scripts/enrich-descriptions-lastmile.py --limit 100
"""

import json
import re
import time
from html.parser import HTMLParser
from urllib.request import urlopen, Request
from urllib.parse import quote_plus

from enrichment_base import EnrichmentScript
from enrichment_config import USER_AGENT


class TextExtractor(HTMLParser):
    """Extract plain text paragraphs from HTML."""
    def __init__(self):
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
            # Only keep substantial paragraphs
            if len(text) > 50 and not text.startswith("***"):
                self._paragraphs.append(text)

    def handle_data(self, data):
        if self._in_p:
            self._current += data

    @property
    def paragraphs(self) -> list[str]:
        return self._paragraphs


class LastMileEnricher(EnrichmentScript):
    source_name = "lastmile_desc"
    enrichment_field = "description"

    def search(self, book: dict) -> dict | None:
        # Strategy 1: Gutenberg full-text first paragraphs
        gid = book.get("gutenberg_id")
        if gid:
            desc = self._try_gutenberg_text(gid)
            if desc:
                return {"description": desc}

        # Strategy 2: Open Library editions
        ol_url = book.get("open_library_url", "")
        if ol_url:
            desc = self._try_ol_editions(ol_url)
            if desc:
                return {"description": desc}

        # Strategy 3: Google Books by ISBN
        isbn = book.get("isbn")
        if isbn:
            desc = self._try_google_isbn(isbn)
            if desc:
                return {"description": desc}

        return None

    def _try_gutenberg_text(self, gid: int) -> str | None:
        """Fetch first substantial paragraphs from Gutenberg HTML."""
        url = f"https://www.gutenberg.org/cache/epub/{gid}/pg{gid}-images.html"
        req = Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urlopen(req, timeout=20) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
                parser = TextExtractor()
                parser.feed(html)
                # Take first 2-3 substantial paragraphs
                good = [p for p in parser.paragraphs if not any(
                    skip in p.lower() for skip in [
                        "project gutenberg", "ebook", "copyright",
                        "table of contents", "chapter", "preface",
                        "transcriber", "produced by", "updated editions",
                    ]
                )]
                if good:
                    combined = " ".join(good[:2])
                    if len(combined) > 500:
                        cut = combined[:500].rfind(". ")
                        if cut > 200:
                            combined = combined[:cut + 1]
                    return combined
        except Exception:
            pass
        return None

    def _try_ol_editions(self, ol_url: str) -> str | None:
        """Try Open Library editions for description."""
        # Extract work key from URL like /works/OL12345W
        match = re.search(r"/works/(OL\w+)", ol_url)
        if not match:
            return None
        work_key = match.group(1)

        # Fetch editions list
        url = f"https://openlibrary.org/works/{work_key}/editions.json?limit=5"
        req = Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
                for edition in data.get("entries", []):
                    desc = edition.get("description")
                    if isinstance(desc, dict):
                        desc = desc.get("value", "")
                    if desc and len(desc) > 30:
                        if len(desc) > 500:
                            cut = desc[:500].rfind(". ")
                            if cut > 200:
                                desc = desc[:cut + 1]
                        return desc
        except Exception:
            pass
        return None

    def _try_google_isbn(self, isbn: str) -> str | None:
        """Try Google Books with precise ISBN lookup."""
        url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}&maxResults=1"
        req = Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
                items = data.get("items", [])
                if items:
                    desc = items[0].get("volumeInfo", {}).get("description", "")
                    if desc and len(desc) > 30:
                        # Strip HTML
                        desc = re.sub(r'<[^>]+>', '', desc).strip()
                        if len(desc) > 500:
                            cut = desc[:500].rfind(". ")
                            if cut > 200:
                                desc = desc[:cut + 1]
                        return desc
        except Exception:
            pass
        return None


if __name__ == "__main__":
    LastMileEnricher.cli()
