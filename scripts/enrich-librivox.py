#!/usr/bin/env python3
"""
Enrich book data with LibriVox free audiobook links.

Usage:
  python scripts/enrich-librivox.py              # enrich all books
  python scripts/enrich-librivox.py --limit 500  # batch size
"""

from urllib.parse import quote_plus

from enrichment_base import EnrichmentScript
from enrichment_config import API_URLS
from matching import strip_article, author_last_name, titles_match


class LibriVoxEnricher(EnrichmentScript):
    source_name = "librivox"
    enrichment_field = "librivox_url"

    def search(self, book: dict) -> dict | None:
        title = book["title"]
        author = book["author"]

        if len(title) < 3:
            return None

        search_title = strip_article(title).lower()
        query = quote_plus(search_title)
        url = f"{API_URLS['librivox']}?title={query}&format=json"

        data = self.safe_request(url)
        if not data or "error" in data:
            return None

        books = data.get("books", [])
        if not books:
            return None

        last_name = author_last_name(author)

        for result in books[:10]:
            result_title = result.get("title", "")
            # REQUIRE author match
            for a in result.get("authors", []):
                name = f"{a.get('first_name', '')} {a.get('last_name', '')}".lower().strip()
                if last_name and last_name in name:
                    if titles_match(title, result_title):
                        url_librivox = result.get("url_librivox", "")
                        if url_librivox:
                            return {"librivox_url": url_librivox}

        return None


if __name__ == "__main__":
    LibriVoxEnricher.cli()
