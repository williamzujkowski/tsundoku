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
        entry = {
            "t": d["title"],
            "s": f'{d.get("author", "")} — {d.get("category", "")}',
            "u": f"books/{d['slug']}/",
            "y": "book",
            "c": d.get("cover_url", ""),
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
            entry = {
                "t": d["name"],
                "s": f'{d.get("book_count", 0)} books',
                "u": f"authors/{d['slug']}/",
                "y": "author",
                "c": d.get("photo_url", ""),
            }
            if keywords:
                entry["k"] = " ".join(keywords)
            items.append(entry)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(items, separators=(",", ":")))

    print(f"Search index: {len(items)} items ({OUTPUT.stat().st_size // 1024}KB)")


if __name__ == "__main__":
    main()
