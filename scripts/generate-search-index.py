#!/usr/bin/env python3
"""Generate search-index.json for client-side search.

Instead of embedding 3,500+ books into every page's HTML via
Astro getCollection, generate a single JSON file that the
SearchModal fetches on demand when opened.
"""

import json
from pathlib import Path

BOOKS_DIR = Path(__file__).parent.parent / "src" / "content" / "books"
AUTHORS_DIR = Path(__file__).parent.parent / "src" / "content" / "authors"
OUTPUT = Path(__file__).parent.parent / "public" / "search-index.json"


def main() -> None:
    items = []

    # Books
    for bp in sorted(BOOKS_DIR.glob("*.json")):
        d = json.loads(bp.read_text())
        items.append({
            "t": d["title"],
            "s": f'{d.get("author", "")} — {d.get("category", "")}',
            "u": f"books/{d['slug']}/",
            "y": "book",
            "c": d.get("cover_url", ""),
        })

    # Authors
    if AUTHORS_DIR.exists():
        for ap in sorted(AUTHORS_DIR.glob("*.json")):
            d = json.loads(ap.read_text())
            items.append({
                "t": d["name"],
                "s": f'{d.get("book_count", 0)} books',
                "u": f"authors/{d['slug']}/",
                "y": "author",
                "c": d.get("photo_url", ""),
            })

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(items, separators=(",", ":")))

    print(f"Search index: {len(items)} items ({OUTPUT.stat().st_size // 1024}KB)")


if __name__ == "__main__":
    main()
