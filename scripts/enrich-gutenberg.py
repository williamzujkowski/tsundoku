#!/usr/bin/env python3
"""
Enrich book data with Project Gutenberg links via Gutendex API.

Usage:
  python scripts/enrich-gutenberg.py              # enrich all books
  python scripts/enrich-gutenberg.py --limit 500  # batch size
"""

from urllib.parse import quote_plus

from enrichment_base import EnrichmentScript
from enrichment_config import API_URLS
from matching import author_last_name, titles_match


class GutenbergEnricher(EnrichmentScript):
    source_name = "gutenberg"
    enrichment_field = "gutenberg_url"

    def search(self, book: dict) -> dict | None:
        title = book["title"]
        author = book["author"]
        query = quote_plus(f"{title} {author}")
        url = f"{API_URLS['gutenberg']}?search={query}"

        data = self.safe_request(url)
        if not data:
            return None

        results = data.get("results", [])
        if not results:
            return None

        last_name = author_last_name(author)

        for result in results[:5]:
            result_title = result.get("title", "")
            # REQUIRE author match
            author_matched = any(
                last_name and last_name in a.get("name", "").lower()
                for a in result.get("authors", [])
            )
            if not author_matched:
                continue

            # REQUIRE title similarity
            if titles_match(title, result_title):
                gid = result.get("id")
                if not gid:
                    continue

                fields = {
                    "gutenberg_id": gid,
                    "gutenberg_url": f"https://www.gutenberg.org/ebooks/{gid}",
                }

                # Get reading URL from formats
                formats = result.get("formats", {})
                for mime in ("text/html", "text/html; charset=utf-8"):
                    if mime in formats:
                        fields["gutenberg_read_url"] = formats[mime]
                        break

                return fields

        return None


if __name__ == "__main__":
    GutenbergEnricher.cli()
