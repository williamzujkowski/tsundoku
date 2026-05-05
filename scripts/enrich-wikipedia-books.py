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

        # Wikipedia summaries with these category markers describe
        # something other than the book — even if the rest of the extract
        # mentions "published" or "story". Outright reject; otherwise the
        # 1996 video game *MissionForce: CyberStorm* leaks into Matthew
        # Mather's 2013 novel, which is exactly the kind of regression
        # this enricher exists to avoid.
        NON_BOOK_DESC = re.compile(
            r"\b(video game|computer game|board game|tabletop game|"
            r"first-person shooter|real-time strategy|turn-based strategy|"
            r"role-playing game|MMORPG|platform(?:er)?|fighting game|"
            r"film|movie|television series|TV series|miniseries|"
            r"studio album|debut album|live album|EP|single|song|musical|"
            r"comic series|graphic novel series|"
            r"programming language|operating system|software library|"
            r"website|web framework)\b",
            re.I,
        )

        for wiki_title in candidates:
            result = self._fetch_summary(wiki_title)
            if result:
                extract = result.get("extract", "").lower()
                desc = result.get("description", "").lower()

                # Hard reject: Wikipedia's short `description` field is a
                # tight categorization like "1996 video game" or "2013
                # novel by Matthew Mather". If it names a non-book medium,
                # this is the wrong page no matter what the extract says.
                if NON_BOOK_DESC.search(desc) or NON_BOOK_DESC.search(extract[:300]):
                    continue

                # Accept only on an *explicit* book/literary marker IN
                # the description (Wikipedia's tight categorisation),
                # the description naming the author, or the extract
                # naming both a literary marker AND the author. Without
                # the description-side anchor, articles about the
                # subject (e.g. "The Gallic War" → 58–50 BC conflict)
                # leak in: their extracts trivially contain the
                # author's last name without describing the book.
                BOOK_MARKERS = (
                    "novel", "novella", "book", "poem", "epic poem",
                    "play", "memoir", "essay", "essays", "treatise",
                    "literary", "fiction", "non-fiction", "nonfiction",
                    "anthology", "collection of", "short story",
                    "biography", "autobiography",
                )
                last_name = author.split()[-1].lower() if author else ""
                desc_has_marker = any(kw in desc for kw in BOOK_MARKERS)
                desc_has_author = bool(last_name) and last_name in desc
                extract_head = extract[:300]
                extract_supports = (
                    any(kw in extract_head for kw in BOOK_MARKERS)
                    and (not last_name or last_name in extract_head)
                )
                is_book = desc_has_marker or desc_has_author or extract_supports

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

                    # Use thumbnail as cover if book has none AND the
                    # thumbnail is portrait-shaped — Wikipedia article
                    # leads are often illustrative photos (manuscript
                    # pages, museum artefacts, paintings depicting the
                    # subject) which are landscape and definitely not
                    # book covers. See the regression where The Gallic
                    # War's thumbnail was a 19th-century painting of
                    # Vercingetorix surrendering, 330x220 (aspect 1.50).
                    if not book.get("cover_url"):
                        thumb_obj = result.get("thumbnail") or {}
                        thumb = thumb_obj.get("source")
                        tw, th = thumb_obj.get("width"), thumb_obj.get("height")
                        if thumb and tw and th and th > 0:
                            aspect = tw / th
                            # Books are typically 0.55–0.78 aspect; allow
                            # up to 0.85 for square-ish reprints. Reject
                            # anything wider — that's not a cover.
                            if aspect <= 0.85:
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
