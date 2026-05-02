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
AUTHORS_DIR = Path(__file__).parent.parent / "src" / "content" / "authors"
OUTPUT = Path(__file__).parent.parent / "public" / "browse-data.json"


def main() -> None:
    # Author → primary nationality lookup (Wikidata P27, first entry).
    # Used to attach a nationality filter to each book on the wire.
    primary_nat: dict[str, str] = {}
    if AUTHORS_DIR.exists():
        for ap in sorted(AUTHORS_DIR.glob("*.json")):
            a = json.loads(ap.read_text())
            nats = a.get("nationality") or []
            if nats:
                primary_nat[a["name"]] = nats[0]

    books = []
    categories = set()
    tag_counts: dict[str, int] = {}
    decade_counts: dict[int, int] = {}
    language_counts: dict[str, int] = {}
    nat_counts: dict[str, int] = {}

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
        if d.get("first_published") is not None:
            entry["y"] = d["first_published"]
            decade = (d["first_published"] // 10) * 10
            decade_counts[decade] = decade_counts.get(decade, 0) + 1
        if d.get("reading_status"):
            entry["rs"] = d["reading_status"]
        lcc = d.get("lcc") or []
        if lcc:
            entry["lc"] = lcc[0]
        tags = d.get("tags") or []
        if tags:
            entry["g"] = tags
            for t in tags:
                tag_counts[t] = tag_counts.get(t, 0) + 1
        # Original language (when set, indicates a non-English work)
        if d.get("original_language"):
            entry["ol"] = d["original_language"]
            language_counts[d["original_language"]] = language_counts.get(d["original_language"], 0) + 1
        # Author primary nationality (lookup table from authors dir)
        nat = primary_nat.get(d.get("author", ""))
        if nat:
            entry["n"] = nat
            nat_counts[nat] = nat_counts.get(nat, 0) + 1
        if entry["cat"]:
            categories.add(entry["cat"])
        books.append(entry)

    # Decade options: every populated decade with ≥1 book, sorted ascending
    decades = sorted(decade_counts.keys())

    # Language options: top by count, alphabetized for the dropdown
    languages = sorted(language_counts.keys())

    # Nationality options: top 30 by count (long tail not useful in a dropdown)
    nationalities = sorted(nat_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:30]

    payload = {
        "books": books,
        "categories": sorted(categories),
        "tags": [t for t, _ in sorted(tag_counts.items(), key=lambda kv: (-kv[1], kv[0]))],
        "decades": decades,
        "languages": languages,
        "nationalities": [code for code, _ in nationalities],
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, separators=(",", ":")))

    size_kb = OUTPUT.stat().st_size / 1024
    print(
        f"Browse data: {len(books)} books, "
        f"{len(payload['categories'])} categories, "
        f"{len(payload['tags'])} tags, "
        f"{len(decades)} decades, "
        f"{len(languages)} languages, "
        f"{len(payload['nationalities'])} nationalities "
        f"({size_kb:.0f}KB)"
    )


if __name__ == "__main__":
    main()
