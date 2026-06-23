#!/usr/bin/env python3
"""Generate stub author pages for every author referenced in books.

For each book's `author` field we attribute the book to:
  - The full author string (existing behavior — preserves joint-string records like
    "Robert Jordan & Brandon Sanderson" so old URLs still work)
  - Each individual component name when the string is a multi-author entry like
    "Robert Jordan & Brandon Sanderson" → also stub "Robert Jordan" + "Brandon Sanderson"

Component splitting matches the parseAuthors() helper in src/utils/formatting.ts:
each part must be at least two whitespace-separated tokens (avoids splitting
initials).

Run enrich-authors.py + enrich-authors-gaps.py afterward to populate bios + photos.

Usage:
  python scripts/generate-author-stubs.py
"""

import json
import re
from collections import Counter
from pathlib import Path

BOOKS_DIR = Path(__file__).parent.parent / "src" / "content" / "books"
AUTHORS_DIR = Path(__file__).parent.parent / "src" / "content" / "authors"

# Mirror src/utils/formatting.ts parseAuthors() — keep in sync.
# Strong separators always indicate joint authorship — split unconditionally.
STRONG_SEPARATORS = re.compile(r"\s*(?:&| and | with |/)\s*", re.IGNORECASE)
COMMA_SEPARATOR = re.compile(r"\s*,\s*")
# A comma immediately followed by a corporate suffix belongs to an organization
# name ("World Variety Produce, Inc."), not an author separator. Mask it with a
# sentinel (\x00, never present in real names) before splitting so the comma
# splitter ignores it, then restore.
_COMMA_SENTINEL = "\x00"
ORG_SUFFIX_COMMA = re.compile(
    r",(\s*(?:Inc|LLC|Ltd|Corp|Co|GmbH|PLC|LP|LLP)\.?\b)", re.IGNORECASE
)
# Organizational / non-person byline pattern — keep in sync with
# isOrganizationalAuthorName() / ORG_NAME_PATTERN in src/utils/formatting.ts.
# An institutional byline (committee/council/"Various ...") does not decompose
# into people, so it is treated as a single indivisible entity (see #198: the
# "National Research Council, Division ... and ... Committee ..." byline must NOT
# split on the `and`s buried inside its division names).
ORG_NAME_PATTERN = re.compile(
    r"(\bInc\.?\b|\bLLC\b|\bLtd\.?\b|\bCorp\.?\b|\bStaff\b|\bCommittee\b"
    r"|\bCommission\b|\bEditors?\b|\bCouncil\b|\bSociety\b|\bAssociation\b"
    r"|\bFoundation\b|\bInstitute\b|\bBoard\b|^Various\b|\(Various\))",
    re.IGNORECASE,
)
# Parenthetical groups, e.g. "(Arabic/Persian)" — separators inside them are part
# of the name, never author boundaries.
_PARENS = re.compile(r"\([^)]*\)")
# Lowercase connector words appear in org division names ("Division on Earth and
# Life Studies", "Environment and Resources") but never inside a person's name —
# used to tell a person from an institutional sub-unit.
_CONNECTORS = {"on", "of", "the", "and", "for", "in", "de", "la"}


def to_slug(text: str) -> str:
    """Convert text to URL-safe slug."""
    return re.sub(r"(^-|-$)", "", re.sub(r"[^a-z0-9]+", "-", text.lower()))


def _looks_like_person(part: str) -> bool:
    """Heuristic: a comma-part that reads as a personal name (not an org unit)."""
    toks = part.split()
    if not (2 <= len(toks) <= 4):
        return False
    if ORG_NAME_PATTERN.search(part):
        return False
    return not any(t.lower() in _CONNECTORS for t in toks)


def _is_indivisible_org(name: str) -> bool:
    """True for an organizational byline that should NOT be split into people.

    Three signals must all hold (#198):
      * the byline matches the organizational pattern;
      * it has no slash OUTSIDE parentheses — a slash is a deliberate contributor
        separator (the cookbook byline "... / World Variety Produce, Inc."), and
        a slash inside parens ("Various (Arabic/Persian)") is part of the name;
      * fewer than 2 comma-parts look like personal names — so a byline that is an
        org PREFIX followed by real people ("Calm Publications Staff, Kevin Crane,
        Carolyn Thomson, Peter Dans") still splits, while a pure institutional
        byline ("National Research Council, Division ... and ... Committee ...")
        stays one entity.
    """
    if not ORG_NAME_PATTERN.search(name):
        return False
    if "/" in _PARENS.sub("", name):
        return False
    parts = [p.strip() for p in COMMA_SEPARATOR.split(name) if p.strip()]
    person_like = sum(1 for p in parts if _looks_like_person(p))
    return person_like < 2


def _comma_sub_split(segment: str) -> list[str]:
    """Comma-sub-split one strong segment, honoring the 2-token + org guards."""
    masked = ORG_SUFFIX_COMMA.sub(_COMMA_SENTINEL + r"\1", segment)
    raw = [
        p.replace(_COMMA_SENTINEL, ",").strip()
        for p in COMMA_SEPARATOR.split(masked)
        if p.replace(_COMMA_SENTINEL, ",").strip()
    ]
    multi_token = [p for p in raw if len(p.split()) >= 2]
    # Only treat commas as author separators when there's clear evidence of a
    # "First Last, First Last" list: 2+ sub-parts carry 2+ tokens. Otherwise the
    # commas belong to a single name (catalog notation, org suffix, initials).
    return raw if len(multi_token) >= 2 else [segment.strip()]


def split_authors(name: str) -> list[str]:
    """Split a multi-author byline into component names. Returns [name] if not joint.

    Two-phase: split on STRONG separators (kept unconditionally), then
    comma-sub-split each segment when 2+ sub-parts have 2+ tokens. Handles mixed
    "A, B, and C" / "A, B / Org, Inc." bylines (#198). Mirrors parseAuthors().
    """
    if _is_indivisible_org(name):
        return [name]
    strong = [p.strip() for p in STRONG_SEPARATORS.split(name) if p.strip()]
    segments = strong if len(strong) >= 2 else [name]
    parts = [p for seg in segments for p in _comma_sub_split(seg)]
    if len(parts) >= 2:
        return parts
    return [name]


def main() -> None:
    # Per book, attribute to BOTH the full author string AND each component name.
    # Use a set per book so a name doesn't double-count if it appears as both
    # full-string and component (rare but possible).
    counts: Counter[str] = Counter()
    for bp in BOOKS_DIR.glob("*.json"):
        book = json.loads(bp.read_text())
        author_str = book["author"]
        names = {author_str, *split_authors(author_str)}
        for n in names:
            counts[n] += 1

    # Map existing author slug → file path. Most records live at
    # `<slug>.json`, but a record's `slug` field can differ from its filename
    # (e.g. -2 suffixes), so resolve via the record's own slug.
    existing_paths: dict[str, Path] = {}
    for ap in AUTHORS_DIR.glob("*.json"):
        author = json.loads(ap.read_text())
        existing_paths[author.get("slug", "")] = ap

    # Refresh book_count on EVERY existing record. `book_count` is a derived
    # field, so authoritatively overwrite it with the freshly computed
    # attributable count — keyed off each record's own `name` so orphaned
    # records (whose name no longer appears in any book) correctly drop to 0
    # rather than going stale (issue #179). All other fields (bio, photo_url,
    # wikipedia_url, …) are preserved exactly.
    updated = 0
    skipped_existing = 0
    for slug, existing_path in existing_paths.items():
        skipped_existing += 1
        author_data = json.loads(existing_path.read_text())
        count = counts.get(author_data.get("name", ""), 0)
        if author_data.get("book_count") != count:
            author_data["book_count"] = count
            existing_path.write_text(
                json.dumps(author_data, indent=2, ensure_ascii=False) + "\n"
            )
            updated += 1

    # Create stubs for any author identity that has no record yet.
    created = 0
    skipped_unknown = 0
    for name, count in sorted(counts.items()):
        slug = to_slug(name)

        if name == "Unknown":
            skipped_unknown += count
            continue

        if not slug:
            continue  # cyrillic-only names, etc.

        if slug in existing_paths or (AUTHORS_DIR / f"{slug}.json").exists():
            continue

        author_path = AUTHORS_DIR / f"{slug}.json"
        author_data = {
            "name": name,
            "slug": slug,
            "book_count": count,
        }
        author_path.write_text(json.dumps(author_data, indent=2, ensure_ascii=False) + "\n")
        created += 1

    total_authors = len(counts)
    print(f"Distinct author identities (full strings + components): {total_authors}")
    print(f"Existing pages: {skipped_existing}")
    print(f"Created stubs: {created}")
    print(f"Updated book_count on existing records: {updated}")
    if skipped_unknown:
        print(f"Skipped 'Unknown': {skipped_unknown} books")


if __name__ == "__main__":
    main()
