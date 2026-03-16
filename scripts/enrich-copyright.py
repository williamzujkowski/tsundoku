#!/usr/bin/env python3
"""
Compute copyright_status for all books from existing metadata.

No API calls needed — derives status from:
  1. Gutenberg/LibriVox presence → public_domain (guaranteed by platforms)
  2. HathiTrust rights pd/pdus → public_domain
  3. first_published <= 1930 → public_domain (US safe threshold, 95-year rule)
  4. first_published 1931-1963 → likely_public_domain (many copyrights unrenewed)
  5. first_published > 1963 → in_copyright (unless other PD signal)
  6. No data → undetermined

Enum: public_domain | likely_public_domain | in_copyright | undetermined

Usage:
  python scripts/enrich-copyright.py           # dry run
  python scripts/enrich-copyright.py --apply   # write to book JSON files
  python scripts/enrich-copyright.py --report  # show status distribution
"""

from collections import Counter

from enrichment_config import load_all_books, save_book

# Year threshold for safe US public domain determination
# As of 2026: works published <= 1930 are public domain
PD_YEAR_THRESHOLD = 1930
LIKELY_PD_YEAR_END = 1963  # Pre-1964 works often had unrenewed copyrights


def compute_copyright_status(book: dict) -> str:
    """Determine copyright status from existing book metadata.

    Priority order (first match wins):
    1. Platform guarantees (Gutenberg, LibriVox = always PD)
    2. HathiTrust explicit rights codes
    3. Publication year heuristics
    """
    # Signal 1: Gutenberg or LibriVox presence = guaranteed public domain
    if book.get("gutenberg_url") or book.get("librivox_url"):
        return "public_domain"

    # Signal 2: HathiTrust rights codes
    rights = (book.get("hathitrust_rights") or "").lower()
    if rights in ("full view", "pd", "pdus"):
        return "public_domain"
    if rights in ("limited (search-only)", "ic", "ic-world"):
        return "in_copyright"

    # Signal 3: Publication year
    year = book.get("first_published")
    if year is not None:
        if year <= PD_YEAR_THRESHOLD:
            return "public_domain"
        if year <= LIKELY_PD_YEAR_END:
            return "likely_public_domain"
        return "in_copyright"

    return "undetermined"


def copyright_report() -> None:
    """Print distribution of copyright statuses."""
    statuses: Counter[str] = Counter()
    for bp, book in load_all_books():
        status = compute_copyright_status(book)
        statuses[status] += 1

    total = sum(statuses.values())
    print(f"\n{'Status':<25} {'Count':>6} {'%':>6}")
    print("-" * 40)
    for status in ["public_domain", "likely_public_domain", "in_copyright", "undetermined"]:
        count = statuses.get(status, 0)
        pct = round(100 * count / total, 1) if total else 0
        print(f"{status:<25} {count:>6} {pct:>5.1f}%")
    print(f"{'TOTAL':<25} {total:>6}")


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Compute copyright status from metadata")
    parser.add_argument("--apply", action="store_true", help="Write status to book files")
    parser.add_argument("--report", action="store_true", help="Show status distribution")
    args = parser.parse_args()

    if args.report:
        copyright_report()
        return

    changes = 0
    unchanged = 0
    for bp, book in load_all_books():
        status = compute_copyright_status(book)
        current = book.get("copyright_status")

        if current == status:
            unchanged += 1
            continue

        changes += 1
        if args.apply:
            book["copyright_status"] = status
            save_book(bp, book)

    action = "Updated" if args.apply else "Would update"
    print(f"{action} {changes} books ({unchanged} already correct)")

    if not args.apply and changes > 0:
        print("Run with --apply to write changes.")
        copyright_report()


if __name__ == "__main__":
    main()
