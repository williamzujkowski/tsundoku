#!/usr/bin/env python3
"""
Enrich books with HathiTrust Digital Library links.

Uses the HathiTrust Bibliographic API to find digitized full texts.
Searches by OCLC number (most reliable) or ISBN.

Pre-1929 works are likely public domain with free full-text access.
In-copyright works may have limited search-only access.

API: https://catalog.hathitrust.org/api/volumes/brief/oclc/{id}.json

Usage:
  python scripts/enrich-hathitrust.py              # all books with OCLC/ISBN
  python scripts/enrich-hathitrust.py --limit 200  # batch size
"""

import json
import time
from pathlib import Path
from urllib.request import urlopen, Request

BOOKS_DIR = Path(__file__).parent.parent / "src" / "content" / "books"
UA = "Tsundoku/1.0 (https://github.com/williamzujkowski/tsundoku)"


def search_hathitrust(oclc_id: str | None, isbn: str | None) -> dict | None:
    """Search HathiTrust by OCLC number or ISBN."""
    urls = []
    if oclc_id:
        urls.append(f"https://catalog.hathitrust.org/api/volumes/brief/oclc/{oclc_id}.json")
    if isbn:
        urls.append(f"https://catalog.hathitrust.org/api/volumes/brief/isbn/{isbn}.json")

    for url in urls:
        try:
            req = Request(url, headers={"User-Agent": UA})
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                items = data.get("items", [])
                if items:
                    item = items[0]
                    return {
                        "htid": item.get("htid", ""),
                        "rights": item.get("usRightsString", ""),
                        "url": f"https://babel.hathitrust.org/cgi/pt?id={item['htid']}",
                        "record_url": data.get("records", {}).get(
                            list(data.get("records", {}).keys())[0] if data.get("records") else "", {}
                        ).get("recordURL", ""),
                    }
        except Exception:
            continue
    return None


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Enrich with HathiTrust links")
    parser.add_argument("--limit", type=int, default=0, help="Max books to process")
    args = parser.parse_args()

    book_files = sorted(BOOKS_DIR.glob("*.json"))
    candidates = []
    for f in book_files:
        d = json.loads(f.read_text())
        if d.get("hathitrust_url"):
            continue  # Already linked
        if d.get("oclc_id") or d.get("isbn"):
            candidates.append(f)

    print(f"Candidates with OCLC/ISBN (no HathiTrust yet): {len(candidates)}")

    if args.limit > 0:
        candidates = candidates[: args.limit]

    found = 0
    for i, bp in enumerate(candidates, 1):
        d = json.loads(bp.read_text())
        print(f"[{i}/{len(candidates)}] {d['title']}...", end=" ", flush=True)

        result = search_hathitrust(d.get("oclc_id"), d.get("isbn"))

        if result and result.get("htid"):
            d["hathitrust_url"] = result["url"]
            d["hathitrust_rights"] = result["rights"]
            bp.write_text(json.dumps(d, indent=2, ensure_ascii=False))
            found += 1
            rights = result.get("rights", "unknown")
            print(f"✓ ({rights})")
        else:
            print("—")

        time.sleep(0.5)

    print(f"\nDone: {found} HathiTrust links added")


if __name__ == "__main__":
    main()
