#!/usr/bin/env python3
"""
Last-resort description enrichment from multiple fallback sources.

For books that Wikipedia, Open Library search, and Google Books all missed:
1. Open Library Works API (deeper metadata than search)
2. Open Library author works listing
3. Gutendex first-sentence extraction (for Gutenberg books)

Usage:
  python scripts/enrich-descriptions-fallback.py --limit 200
"""

import json
import time
from urllib.request import urlopen, Request
from urllib.parse import quote_plus, quote

from enrichment_base import EnrichmentScript
from enrichment_config import USER_AGENT


class DescriptionFallbackEnricher(EnrichmentScript):
    source_name = "description_fallback"
    enrichment_field = "description"

    def search(self, book: dict) -> dict | None:
        title = book["title"]
        author = book["author"]

        # Strategy 1: Open Library search with fields=first_sentence
        desc = self._try_ol_first_sentence(title, author)
        if desc:
            return {"description": desc}

        # Strategy 2: Open Library Works API (if we have an OL key)
        desc = self._try_ol_works(title, author)
        if desc:
            return {"description": desc}

        return None

    def _try_ol_first_sentence(self, title: str, author: str) -> str | None:
        """Try Open Library search for first_sentence field."""
        query = quote_plus(f"{title} {author}")
        url = f"https://openlibrary.org/search.json?q={query}&fields=title,author_name,first_sentence,key&limit=3"
        req = Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
                for doc in data.get("docs", [])[:3]:
                    sentences = doc.get("first_sentence", [])
                    if sentences and len(sentences[0]) > 20:
                        return sentences[0]
        except Exception:
            pass
        return None

    def _try_ol_works(self, title: str, author: str) -> str | None:
        """Try Open Library Works API for description."""
        # First find the work key via search
        query = quote_plus(f"{title} {author}")
        url = f"https://openlibrary.org/search.json?q={query}&fields=key&limit=1"
        req = Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
                docs = data.get("docs", [])
                if not docs:
                    return None
                work_key = docs[0].get("key", "")
                if not work_key:
                    return None

            # Fetch the works endpoint
            time.sleep(0.5)
            works_url = f"https://openlibrary.org{work_key}.json"
            req2 = Request(works_url, headers={"User-Agent": USER_AGENT})
            with urlopen(req2, timeout=15) as resp2:
                work = json.loads(resp2.read())
                desc = work.get("description")
                if isinstance(desc, dict):
                    desc = desc.get("value", "")
                if desc and len(desc) > 30:
                    # Truncate to ~500 chars at sentence boundary
                    if len(desc) > 500:
                        cut = desc[:500].rfind(". ")
                        if cut > 200:
                            desc = desc[:cut + 1]
                    return desc
        except Exception:
            pass
        return None


if __name__ == "__main__":
    DescriptionFallbackEnricher.cli()
