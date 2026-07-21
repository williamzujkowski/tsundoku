#!/usr/bin/env python3
"""Generate search-index.json for client-side search.

Instead of embedding 3,500+ books into every page's HTML via
Astro getCollection, generate a single JSON file that the
SearchModal fetches on demand when opened.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from image_guard import resolve_image_url

BOOKS_DIR = Path(__file__).parent.parent / "src" / "content" / "books"
AUTHORS_DIR = Path(__file__).parent.parent / "src" / "content" / "authors"
OUTPUT = Path(__file__).parent.parent / "public" / "search-index.json"
# Tiny companion index: just the book URL paths, so RandomBook.svelte can
# pick a random book without downloading the full ~1MB search index (#203).
RANDOM_SLUGS_OUTPUT = Path(__file__).parent.parent / "public" / "random-slugs.json"


def main() -> None:
    items = []

    # Books — `k` is a hidden keyword bag the search modal also queries,
    # so users can find "1984" by typing "Big Brother" (translator),
    # "Wheel of Time" (series), "Umibe no Kafuka" (original title), etc.
    for bp in sorted(BOOKS_DIR.glob("*.json")):
        d = json.loads(bp.read_text())
        keywords: list[str] = []
        if d.get("original_title") and d["original_title"] != d["title"]:
            keywords.append(d["original_title"])
        series = d.get("series") or {}
        if series.get("name"):
            keywords.append(series["name"])
        if d.get("translator"):
            keywords.append(d["translator"])
        # First subject_facet entry is often a recognizable theme tag
        for s in (d.get("subject_facet") or [])[:3]:
            keywords.append(s)
        # Guard against a /cached/ URL whose file doesn't actually exist in
        # THIS build (see image_guard.py's docstring — the
        # william-shakespeare production 404). Falls back to the
        # preserved upstream source, or "" (the search modal already
        # treats a falsy `c` as "show the placeholder glyph").
        cover_src = resolve_image_url(d.get("cover_url"), d.get("cover_url_source")) or ""
        entry = {
            "t": d["title"],
            "s": f'{d.get("author", "")} — {d.get("category", "")}',
            "u": f"books/{d['slug']}/",
            "y": "book",
            "c": cover_src,
        }
        if keywords:
            entry["k"] = " ".join(keywords)
        items.append(entry)

    # Authors — `k` includes alternate_names so users can find George Eliot
    # by typing "Mary Ann Evans".
    if AUTHORS_DIR.exists():
        for ap in sorted(AUTHORS_DIR.glob("*.json")):
            d = json.loads(ap.read_text())
            keywords: list[str] = []
            for n in (d.get("alternate_names") or []):
                if n and n.lower() != d["name"].lower():
                    keywords.append(n)
            photo_src = resolve_image_url(d.get("photo_url"), d.get("photo_url_source")) or ""
            entry = {
                "t": d["name"],
                "s": f'{d.get("book_count", 0)} books',
                "u": f"authors/{d['slug']}/",
                "y": "author",
                "c": photo_src,
            }
            if keywords:
                entry["k"] = " ".join(keywords)
            items.append(entry)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(items, separators=(",", ":")))

    print(f"Search index: {len(items)} items ({OUTPUT.stat().st_size // 1024}KB)")

    # Companion random-slugs index: book URL paths only.
    book_urls = [item["u"] for item in items if item["y"] == "book"]
    RANDOM_SLUGS_OUTPUT.write_text(json.dumps(book_urls, separators=(",", ":")))
    print(
        f"Random slugs: {len(book_urls)} books "
        f"({RANDOM_SLUGS_OUTPUT.stat().st_size // 1024}KB)"
    )


if __name__ == "__main__":
    main()
