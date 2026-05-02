#!/usr/bin/env python3
"""Generate browse-data.json for the Browse page's BookGrid island.

Same pattern as search-index.json: instead of inlining 3,644 books'
worth of props into every page's HTML (current /browse/ ships ~1.9 MB),
we ship a small page shell and let the island fetch this JSON on mount.

Short field names keep the wire size small. BookGrid maps them to the
internal type when consuming.
"""

import json
from pathlib import Path

BOOKS_DIR = Path(__file__).parent.parent / "src" / "content" / "books"
OUTPUT = Path(__file__).parent.parent / "public" / "browse-data.json"


def main() -> None:
    books = []
    categories = set()
    tag_counts: dict[str, int] = {}

    for bp in sorted(BOOKS_DIR.glob("*.json")):
        d = json.loads(bp.read_text())
        entry = {
            "t": d["title"],
            "a": d.get("author", ""),
            "s": d["slug"],
            "p": d.get("priority", 3),
            "cat": d.get("category", ""),
        }
        # Only include optional fields when set — fewer null bytes on the wire.
        if d.get("cover_url"):
            entry["co"] = d["cover_url"]
        if d.get("first_published"):
            entry["y"] = d["first_published"]
        if d.get("reading_status"):
            entry["rs"] = d["reading_status"]
        # First LCC class only (e.g. "PR-6029.00000000.R8 Ni2") — used as
        # a spine-label on the book card. Browse-grid renders the human-
        # readable form via the same JS `lccDisplay` shape used on book
        # detail pages.
        lcc = d.get("lcc") or []
        if lcc:
            entry["lc"] = lcc[0]
        tags = d.get("tags") or []
        if tags:
            entry["g"] = tags
            for t in tags:
                tag_counts[t] = tag_counts.get(t, 0) + 1
        if entry["cat"]:
            categories.add(entry["cat"])
        books.append(entry)

    payload = {
        "books": books,
        "categories": sorted(categories),
        # Tags sorted by frequency descending (matches existing UI behavior).
        "tags": [t for t, _ in sorted(tag_counts.items(), key=lambda kv: (-kv[1], kv[0]))],
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, separators=(",", ":")))

    size_kb = OUTPUT.stat().st_size / 1024
    print(
        f"Browse data: {len(books)} books, "
        f"{len(payload['categories'])} categories, "
        f"{len(payload['tags'])} tags ({size_kb:.0f}KB)"
    )


if __name__ == "__main__":
    main()
