#!/usr/bin/env python3
"""
Enrich books with descriptions from Wikipedia.

Fallback for books where Open Library and Google Books lack descriptions.
Uses the Wikipedia REST API to fetch article extracts by title.

Also enriches: cover images (from Wikipedia thumbnail) when missing.

Usage:
  python scripts/enrich-wikipedia-books.py              # all books missing descriptions
  python scripts/enrich-wikipedia-books.py --limit 200  # batch size
"""

import re
from urllib.parse import quote

from enrichment_base import EnrichmentScript
from enrichment_config import API_URLS
from matching import strip_article


class WikipediaBookEnricher(EnrichmentScript):
    source_name = "wikipedia_books"
    enrichment_field = "description"

    def search(self, book: dict) -> dict | None:
        title = book["title"]
        author = book["author"]

        # Try multiple Wikipedia title formats
        candidates = [
            title,                                    # Exact title
            f"{title} (novel)",                       # Common disambiguation
            f"{title} (book)",                        # Non-fiction
            f"{title} ({author} novel)",              # Author-specific
            f"{title} (poem)",                        # Poetry
            f"{title} (play)",                        # Drama
        ]

        for wiki_title in candidates:
            result = self._fetch_summary(wiki_title)
            if result:
                # Verify it's about the right book/work (not a film, song, etc.)
                extract = result.get("extract", "").lower()
                desc = result.get("description", "").lower()

                # Accept if description mentions book/literary terms
                is_book = any(kw in desc + " " + extract[:200] for kw in [
                    "novel", "book", "poem", "play", "epic", "story", "work",
                    "collection", "memoir", "essay", "treatise", "written",
                    "published", "author", "literary", "fiction", "tale",
                    author.split()[-1].lower(),  # Author last name in text
                ])

                if is_book and len(result.get("extract", "")) > 50:
                    fields: dict = {}

                    # Use extract as description (truncate to ~500 chars)
                    extract_text = result["extract"]
                    if len(extract_text) > 500:
                        # Cut at sentence boundary
                        cut = extract_text[:500].rfind(". ")
                        if cut > 200:
                            extract_text = extract_text[:cut + 1]
                    fields["description"] = extract_text

                    # Use thumbnail as cover if book has none
                    if not book.get("cover_url"):
                        thumb = result.get("thumbnail", {}).get("source")
                        if thumb:
                            fields["cover_url"] = thumb

                    return fields

        return None

    def _fetch_summary(self, title: str) -> dict | None:
        """Fetch Wikipedia page summary."""
        encoded = quote(title.replace(" ", "_"))
        url = f"{API_URLS['wikipedia']}/{encoded}"
        data = self.safe_request(url)
        if not data:
            return None
        # Skip disambiguation pages
        if data.get("type") == "disambiguation":
            return None
        return data


if __name__ == "__main__":
    WikipediaBookEnricher.cli()
