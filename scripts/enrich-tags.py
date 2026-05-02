#!/usr/bin/env python3
"""
Populate book tags from subject metadata for genre discovery.

Maps Open Library subject strings to normalized genre tags.
Books keep their primary category but gain discoverable genre tags
for filtering and browsing.

Usage:
  python scripts/enrich-tags.py           # dry run
  python scripts/enrich-tags.py --apply   # write tags to book files
  python scripts/enrich-tags.py --report  # show tag distribution
"""

from collections import Counter

from enrichment_config import load_all_books, save_book

# Subject keyword → normalized tag
# Order matters: first match wins for overlapping patterns
SUBJECT_TAG_MAP: list[tuple[str, str]] = [
    # Genre fiction
    ("science fiction", "sci-fi"),
    ("fantasy", "fantasy"),
    ("mystery", "mystery"),
    ("detective", "mystery"),
    ("horror", "horror"),
    ("thriller", "thriller"),
    ("suspense", "thriller"),
    ("romance", "romance"),
    ("adventure", "adventure"),
    ("historical fiction", "historical-fiction"),
    ("fiction, historical", "historical-fiction"),
    ("dystopi", "dystopian"),
    ("utopi", "utopian"),
    ("satire", "satire"),
    ("humor", "humor"),
    ("comic", "humor"),
    ("war fiction", "war"),
    ("war stories", "war"),
    ("ghost stor", "horror"),
    ("supernatural", "horror"),
    ("spy", "espionage"),
    ("espionage", "espionage"),

    # Non-fiction signals
    ("biography", "biography"),
    ("autobiograph", "biography"),
    ("memoir", "memoir"),
    ("philosophy", "philosophy"),
    ("psychology", "psychology"),
    ("economics", "economics"),
    ("political science", "politics"),
    ("mathematics", "math"),
    ("computer", "computing"),
    ("programming", "computing"),
    ("software", "computing"),
    ("artificial intelligence", "ai"),
    ("machine learning", "ai"),
    ("cryptography", "security"),
    ("cybersecurity", "security"),
    ("physics", "physics"),
    ("chemistry", "chemistry"),
    ("biology", "biology"),
    ("evolution", "biology"),
    ("ecology", "ecology"),
    ("astronomy", "astronomy"),
    ("cosmology", "astronomy"),

    # Audience/form
    ("children", "children"),
    ("juvenile", "children"),
    ("young adult", "young-adult"),
    ("poetry", "poetry"),
    ("drama", "drama"),
    ("play", "drama"),
    ("short stor", "short-stories"),
    ("essay", "essays"),
]


def extract_tags(subjects: list[str]) -> list[str]:
    """Extract normalized tags from a list of subject strings."""
    tags = set()
    for subject in subjects:
        sl = subject.lower()
        for keyword, tag in SUBJECT_TAG_MAP:
            if keyword in sl:
                tags.add(tag)
    return sorted(tags)


def tag_report() -> None:
    """Show distribution of extracted tags."""
    tag_counts: Counter[str] = Counter()
    books_with_tags = 0
    total = 0

    for bp, book in load_all_books():
        total += 1
        subjects = book.get("subject_facet") or []
        if subjects:
            tags = extract_tags(subjects)
            if tags:
                books_with_tags += 1
                for t in tags:
                    tag_counts[t] += 1

    print(f"\nBooks with extractable tags: {books_with_tags}/{total} ({100*books_with_tags/total:.1f}%)\n")
    print(f"{'Tag':<20} {'Count':>6}")
    print("-" * 28)
    for tag, count in tag_counts.most_common():
        print(f"{tag:<20} {count:>6}")


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Populate tags from subjects")
    parser.add_argument("--apply", action="store_true", help="Write tags to book files")
    parser.add_argument("--report", action="store_true", help="Show tag distribution")
    args = parser.parse_args()

    if args.report:
        tag_report()
        return

    updated = 0
    unchanged = 0
    for bp, book in load_all_books():
        subjects = book.get("subject_facet") or []
        if not subjects:
            continue

        new_tags = extract_tags(subjects)
        existing = set(book.get("tags", []))
        merged = sorted(existing | set(new_tags))

        if merged == sorted(existing):
            unchanged += 1
            continue

        updated += 1
        if args.apply:
            book["tags"] = merged
            save_book(bp, book)

    action = "Updated" if args.apply else "Would update"
    print(f"{action} {updated} books ({unchanged} already have these tags)")
    if not args.apply and updated > 0:
        print("Run with --apply to write changes.")


if __name__ == "__main__":
    main()
