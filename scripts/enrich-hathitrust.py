#!/usr/bin/env python3
"""
Enrich books with HathiTrust Digital Library links.
Searches by OCLC number (most reliable) or ISBN.

Usage:
  python scripts/enrich-hathitrust.py              # all books with OCLC/ISBN
  python scripts/enrich-hathitrust.py --limit 200  # batch size
"""

from enrichment_base import EnrichmentScript
from enrichment_config import API_URLS


class HathiTrustEnricher(EnrichmentScript):
    source_name = "hathitrust"
    enrichment_field = "hathitrust_url"

    def filter_unenriched(self, books):
        """Override: only process books with OCLC or ISBN but no HathiTrust link."""
        return [
            (bp, b) for bp, b in books
            if not b.get("hathitrust_url") and (b.get("oclc_id") or b.get("isbn"))
        ]

    def search(self, book: dict) -> dict | None:
        oclc_id = book.get("oclc_id")
        isbn = book.get("isbn")

        # Try OCLC first (most reliable), then ISBN
        lookup_ids = []
        if oclc_id:
            lookup_ids.append(("oclc", oclc_id))
        if isbn:
            lookup_ids.append(("isbn", isbn))

        for id_type, id_value in lookup_ids:
            url = f"{API_URLS['hathitrust']}/{id_type}/{id_value}.json"
            data = self.safe_request(url)
            if not data:
                continue

            items = data.get("items", [])
            if not items:
                continue

            item = items[0]
            htid = item.get("htid", "")
            if not htid:
                continue

            return {
                "hathitrust_url": f"https://babel.hathitrust.org/cgi/pt?id={htid}",
                "hathitrust_rights": item.get("usRightsString", ""),
            }

        return None


if __name__ == "__main__":
    HathiTrustEnricher.cli()
