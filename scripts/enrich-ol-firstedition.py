#!/usr/bin/env python3
"""Anchor each book to its first-edition metadata (epic #124 phase A).

For every book that has an `ol_work_key`, fetches the work's full editions
list from `/works/{key}/editions.json`, identifies the earliest publication
year by parsing each edition's `publish_date`, and writes:

  • first_published         — work's earliest year (overwrites if our
                              source rank exceeds the prior provenance;
                              fills empties unconditionally)
  • first_published_circa   — true when the earliest year is approximate
                              ("ca. 1850", "[1900?]", "19th century")
  • original_title          — title of the earliest edition that matches
                              the work's original language
  • original_language       — ISO 639-3 of the earliest non-translation edition
  • original_publisher      — publishers[0] of that edition
  • original_pages          — number_of_pages of that edition (if known)
  • first_edition_isbn      — ISBN-13 of that edition; explicit `null` for
                              works whose first edition pre-dates ISBNs
                              (we mark this when first_published < 1970)
  • editions_count          — total editions known to OL
  • representative_edition_key — the OL edition we link to for "find a copy"

The representative edition is chosen as follows:
  1. If the book already has an `isbn`, find the edition with that ISBN.
  2. Otherwise, prefer the most recent edition that has BOTH an ISBN-13
     and a known page count, in the user's preferred language (English
     by default for this catalog).
  3. Fallback: the most recent edition with any ISBN.
  4. Fallback: the most recent edition with a known year.

Provenance: writes are tagged `ol_firstedition_v1` (rank 80). May overwrite
fields that are currently rank ≤ 60 (e.g. `ol_classification_v2`) or
untagged (legacy). Manual edits (rank 100) are preserved.

Usage:
  python scripts/enrich-ol-firstedition.py             # dry-run report
  python scripts/enrich-ol-firstedition.py --apply     # write changes
  python scripts/enrich-ol-firstedition.py --apply --limit 50
  python scripts/enrich-ol-firstedition.py --apply --slug 1984
"""

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen, Request

sys.path.insert(0, str(Path(__file__).parent))

from edition_date import parse_publish_date
from enrichment_config import BOOKS_DIR, USER_AGENT
from http_cache import cached_fetch
from json_merge import provenance_merge, save_json


REQUEST_TIMEOUT = 20
RATE_LIMIT_S = 0.5
EDITIONS_PER_PAGE = 200      # OL caps near 1000; 200 is plenty for most works
MAX_EDITIONS = 400           # hard cap to avoid huge fetches on omnibus works
ISBN_INTRODUCTION_YEAR = 1970  # before this, first_edition_isbn is null

# Quality gate: when many editions claim the first-publication year, OL
# tagging has been smeared across reprints (e.g. Signet paperbacks dated
# 1949 alongside the actual 1949 Secker & Warburg first). Only derive
# original_publisher / original_pages / original_title / original_language
# when the matching set is small enough to be trustworthy.
MAX_MATCHING_FOR_TRUST = 3

SOURCE = "ol_firstedition_v1"

# Fields this enricher is permitted to overwrite when its rank exceeds the
# existing provenance. Other fields it only fills when empty.
FIELDS_OVERWRITABLE = frozenset({
    "first_published",
    "first_published_circa",
    "editions_count",
})

PREFERRED_LANGUAGE = "eng"  # for picking representative edition


def _fetch_json(url: str) -> dict | None:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            return json.loads(resp.read())
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None


def fetch_editions(work_key: str) -> list[dict]:
    """Fetch all editions for an OL work key. Returns list of edition dicts."""
    if not work_key:
        return []
    base = f"https://openlibrary.org{work_key}/editions.json"
    cache_key = f"editions:{work_key}"
    url = f"{base}?limit={EDITIONS_PER_PAGE}"

    data = cached_fetch(
        "ol_work_editions_v1",
        cache_key,
        lambda: _fetch_json(url),
        url=url,
    )
    if not data:
        return []
    entries = data.get("entries") or []
    if len(entries) >= EDITIONS_PER_PAGE and (data.get("size") or 0) > EDITIONS_PER_PAGE:
        # Paginate — cap at MAX_EDITIONS total
        offset = EDITIONS_PER_PAGE
        while offset < min(MAX_EDITIONS, data.get("size", 0)):
            page_url = f"{base}?limit={EDITIONS_PER_PAGE}&offset={offset}"
            page_key = f"editions:{work_key}:offset={offset}"
            page_data = cached_fetch(
                "ol_work_editions_v1",
                page_key,
                lambda u=page_url: _fetch_json(u),
                url=page_url,
            )
            if not page_data:
                break
            entries.extend(page_data.get("entries") or [])
            offset += EDITIONS_PER_PAGE
            time.sleep(0.2)
    return entries


def edition_year(edition: dict) -> tuple[int | None, bool]:
    return parse_publish_date(edition.get("publish_date"))


def edition_lang_codes(edition: dict) -> list[str]:
    """Extract language codes (e.g. "eng") from edition.languages."""
    out = []
    for entry in edition.get("languages") or []:
        key = (entry or {}).get("key", "")
        if key.startswith("/languages/"):
            out.append(key.split("/")[-1])
    return out


def edition_isbn13(edition: dict) -> str | None:
    isbns = edition.get("isbn_13") or []
    return isbns[0] if isbns else None


def edition_any_isbn(edition: dict) -> str | None:
    return edition_isbn13(edition) or ((edition.get("isbn_10") or [None])[0])


def edition_translator(edition: dict) -> str | None:
    """Extract translator name from contributors[].role==Translator."""
    for c in edition.get("contributors") or []:
        if (c or {}).get("role", "").lower().startswith("translator"):
            return c.get("name")
    return None


def is_translation(edition: dict) -> bool:
    return bool(edition.get("translation_of") or edition.get("translated_from"))


def determine_target_year(editions: list[dict], known_first_year: int | None) -> int | None:
    """Pick the year that the 'first edition' should match.

    OL editions data is dirty — Russian reprints with `publish_date: "19--"`
    parse to year 1900, beating a legitimate 1949 first edition. And
    ancient works only show up as 18th/19th-century printed translations.
    This filter keeps the first-edition selection honest:

    * If `known_first_year` is set (from a prior search.json pass), trust
      it as the floor unless 2+ precise-year editions agree on an earlier
      year (then go earlier).
    * If `known_first_year` is unset: don't try to derive one from editions
      alone. Editions data systematically misses ancient/pre-press works
      and the earliest catalogued edition is often a much-later reprint.
      Wikidata enrichment (Phase B) is the right source for those.
    """
    if known_first_year is None:
        return None
    precise: list[int] = []
    for ed in editions:
        y, circa = edition_year(ed)
        if y is None or circa:
            continue
        precise.append(y)
    if not precise:
        return known_first_year
    counts: dict[int, int] = {}
    for y in precise:
        counts[y] = counts.get(y, 0) + 1
    earlier_consensus = [y for y, c in counts.items() if y < known_first_year and c >= 2]
    if earlier_consensus:
        return min(earlier_consensus)
    return known_first_year


def matching_editions(editions: list[dict], target_year: int | None) -> list[dict]:
    """Editions whose parsed year is within ±1 of target_year."""
    if target_year is None:
        return []
    out = []
    for ed in editions:
        y, _ = edition_year(ed)
        if y is not None and abs(y - target_year) <= 1:
            out.append(ed)
    return out


def pick_first_edition(matching: list[dict], target_year: int | None) -> dict | None:
    """Pick the most canonical from a matching-year set.

    Prefers non-translations with full metadata. Only useful when caller
    has already vetted that `matching` is small enough to be trustworthy.
    """
    if not matching or target_year is None:
        return None

    def rank(ed: dict) -> tuple[int, ...]:
        y, circa = edition_year(ed)
        return (
            1 if y == target_year else 0,
            0 if is_translation(ed) else 1,
            0 if circa else 1,
            1 if (ed.get("publishers") or []) else 0,
            1 if ed.get("number_of_pages") else 0,
            1 if edition_any_isbn(ed) else 0,
        )

    return sorted(matching, key=rank, reverse=True)[0]


def pick_representative_edition(
    editions: list[dict],
    *,
    book_isbn: str | None,
    preferred_language: str = PREFERRED_LANGUAGE,
) -> dict | None:
    """The edition we link to for 'find a copy.'

    Order:
      1. Edition matching the book's existing ISBN
      2. Most recent English edition with ISBN-13 and pages
      3. Most recent English edition with any ISBN
      4. Most recent edition with any ISBN
      5. Most recent edition with a year
    """
    if not editions:
        return None

    # 1. Match on existing ISBN
    if book_isbn:
        target = book_isbn.replace("-", "").strip()
        for ed in editions:
            for isbn in (ed.get("isbn_13") or []) + (ed.get("isbn_10") or []):
                if isbn and isbn.replace("-", "").strip() == target:
                    return ed

    def year(ed: dict) -> int:
        y, _ = edition_year(ed)
        return y if y is not None else -10000

    # 2. English + ISBN-13 + pages
    candidates = [
        ed for ed in editions
        if preferred_language in edition_lang_codes(ed)
        and edition_isbn13(ed)
        and ed.get("number_of_pages")
    ]
    if candidates:
        return max(candidates, key=year)

    # 3. English + any ISBN
    candidates = [
        ed for ed in editions
        if preferred_language in edition_lang_codes(ed) and edition_any_isbn(ed)
    ]
    if candidates:
        return max(candidates, key=year)

    # 4. Any edition with ISBN
    candidates = [ed for ed in editions if edition_any_isbn(ed)]
    if candidates:
        return max(candidates, key=year)

    # 5. Anything with a year
    candidates = [ed for ed in editions if edition_year(ed)[0] is not None]
    if candidates:
        return max(candidates, key=year)

    return editions[0]


def derive_fields(work_editions: list[dict], book: dict) -> dict:
    """Compute the field updates for a single book."""
    if not work_editions:
        return {}

    known_first_year = book.get("first_published")
    target_year = determine_target_year(work_editions, known_first_year)

    matching = matching_editions(work_editions, target_year)
    first = pick_first_edition(matching, target_year)
    rep = pick_representative_edition(
        work_editions, book_isbn=book.get("isbn"),
    )

    out: dict = {"editions_count": len(work_editions)}

    if target_year is not None:
        out["first_published"] = target_year

    # Conservative: OL editions are too noisy to derive original_publisher
    # and original_pages reliably (mis-dated reprints corrupt the picked
    # first-edition record for famous works). Phase B (Wikidata) is the
    # canonical source for those — Wikidata has structured P123/P1104.
    #
    # We DO derive:
    #   * first_published_circa from picked first edition
    #   * original_language and original_title — only when picked edition
    #     is a non-English non-translation, since that's the strong-signal
    #     translation case where the user benefits from seeing the original.
    #   * first_edition_isbn from picked edition (when matching set small)
    #     OR explicit null (when target year pre-dates ISBNs).
    if first is not None:
        _, circa = edition_year(first)
        out["first_published_circa"] = bool(circa)

        if not is_translation(first):
            langs = edition_lang_codes(first)
            if langs and langs[0] != "eng":
                # Non-English first edition — the strong-signal translation case.
                out["original_language"] = langs[0]
                full_title = first.get("full_title") or first.get("title")
                if full_title and full_title != book.get("title"):
                    out["original_title"] = full_title

        if len(matching) <= MAX_MATCHING_FOR_TRUST:
            first_isbn = edition_isbn13(first) or edition_any_isbn(first)
            if first_isbn:
                out["first_edition_isbn"] = first_isbn
            elif target_year is not None and target_year < ISBN_INTRODUCTION_YEAR:
                out["first_edition_isbn"] = None
        elif target_year is not None and target_year < ISBN_INTRODUCTION_YEAR:
            out["first_edition_isbn"] = None
    elif target_year is not None and target_year < ISBN_INTRODUCTION_YEAR:
        out["first_edition_isbn"] = None

    if rep:
        out["representative_edition_key"] = rep.get("key")
        translator = edition_translator(rep)
        if translator:
            out["translator"] = translator

    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Anchor books to first-edition metadata")
    parser.add_argument("--apply", action="store_true", help="Write changes to disk")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--slug", help="Process only this book slug (for testing)")
    parser.add_argument(
        "--missing-only",
        action="store_true",
        help="Only books missing original_* / first_edition_isbn / editions_count",
    )
    parser.add_argument(
        "--report-overwrites",
        action="store_true",
        help="Show every overwrite, not just summary",
    )
    args = parser.parse_args()

    files = sorted(BOOKS_DIR.glob("*.json"))
    candidates: list[tuple[Path, dict]] = []
    for f in files:
        b = json.loads(f.read_text(encoding="utf-8"))
        if args.slug and b.get("slug") != args.slug:
            continue
        if not b.get("ol_work_key"):
            continue  # need a work key to query editions
        if args.missing_only:
            already = (
                b.get("editions_count")
                and (b.get("original_publisher") or b.get("first_edition_isbn") is not None)
            )
            if already:
                continue
        candidates.append((f, b))

    if args.limit:
        candidates = candidates[: args.limit]

    print(f"Processing {len(candidates)} books with ol_work_key")

    n_filled = 0
    n_overwrites = 0
    n_no_match = 0
    counters: dict[str, int] = {}
    overwrite_audit: list[tuple[str, dict]] = []

    for i, (path, book) in enumerate(candidates, 1):
        editions = fetch_editions(book["ol_work_key"])
        time.sleep(RATE_LIMIT_S)

        if not editions:
            n_no_match += 1
            continue

        new_fields = derive_fields(editions, book)
        if not new_fields:
            n_no_match += 1
            continue

        if args.apply:
            changed, audit = provenance_merge(
                book,
                new_fields,
                source=SOURCE,
                fields_overwritable=FIELDS_OVERWRITABLE,
            )
            if changed:
                save_json(path, book)
                n_filled += 1
            if audit:
                n_overwrites += len(audit)
                overwrite_audit.append((book["slug"], audit))
        else:
            # Dry-run: simulate to count what would change
            sim = dict(book)
            sim["_provenance"] = dict(book.get("_provenance") or {})
            changed, audit = provenance_merge(
                sim, new_fields, source=SOURCE, fields_overwritable=FIELDS_OVERWRITABLE,
            )
            if changed:
                n_filled += 1
            if audit:
                n_overwrites += len(audit)
                overwrite_audit.append((book["slug"], audit))

        for k in new_fields:
            counters[k] = counters.get(k, 0) + 1

        if i % 50 == 0:
            print(
                f"  [{i}/{len(candidates)}] filled={n_filled}  overwrites={n_overwrites}"
                f"  no-match={n_no_match}"
            )

    print(f"\nDone. {n_filled}/{len(candidates)} books got new fields.")
    print(f"Overwrites: {n_overwrites}.  No editions found: {n_no_match}.")
    print("\nField fill counts:")
    for k in sorted(counters):
        print(f"  +{k:30s}  {counters[k]}")

    if args.report_overwrites and overwrite_audit:
        print("\nOverwrite details:")
        for slug, audit in overwrite_audit[:50]:
            for field, change in audit.items():
                print(
                    f"  {slug:40s}  {field}: {change['from']!r} → {change['to']!r}"
                    f"  ({change['old_source'] or 'legacy'} → {change['new_source']})"
                )
        if len(overwrite_audit) > 50:
            print(f"  ... and {len(overwrite_audit) - 50} more")

    if not args.apply:
        print("\nDry-run — pass --apply to write")

    return 0


if __name__ == "__main__":
    sys.exit(main())
