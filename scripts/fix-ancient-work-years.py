#!/usr/bin/env python3
"""Patch first_published for famous ancient works with manual values.

OL editions data systematically misses ancient works (their earliest
catalogued printing is usually the 18th-19th century, not the original
composition). Wikidata's P577 is also sparse for pre-press works.

This script applies hand-curated dates from the standard literary
chronology and tags them with provenance `manual` so subsequent
enrichers can't re-clobber.

GOTCHA: title-only matching breaks for shared titles. The script's
ANCIENT_WORKS table needs to either be tightened to (title, author)
keys before re-running, or the matched results audited by hand. See
the post-mortem patches for Descartes' Meditations (1641, not 170 —
Marcus Aurelius shares the title) and Machiavelli's Art of War (1521,
not -500 — Sun Tzu shares the title).

Usage:
  python scripts/fix-ancient-work-years.py             # dry-run
  python scripts/fix-ancient-work-years.py --apply
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from json_merge import save_json

BOOKS_DIR = Path(__file__).parent.parent / "src" / "content" / "books"

# Hand-curated first-publication years for ancient works. Negative ints
# are BCE. These are the consensus dates from the standard reference
# chronology (Cambridge / OCD / Britannica). Slight uncertainties are
# normal — within ~50 years for most pre-classical works.
ANCIENT_WORKS: dict[str, int] = {
    # Ancient Mediterranean
    'the iliad': -750, 'iliad': -750,
    'the odyssey': -700, 'odyssey': -700,
    'theogony': -700,
    'works and days': -700,
    'aeneid': -29,
    'metamorphoses': 8,
    'natural history': 77,
    'germania': 98,
    'agricola': 98,

    # Greek tragedy/comedy
    'oedipus rex': -429, 'oedipus the king': -429,
    'oedipus at colonus': -401,
    'antigone': -441,
    'lysistrata': -411,
    'the frogs': -405, 'frogs': -405,
    'the clouds': -423,

    # Plato
    'the republic': -380, 'republic': -380,
    'phaedo': -380, 'phaedrus': -370,
    'symposium': -385, 'apology': -399,
    'crito': -360, 'gorgias': -380, 'timaeus': -360,
    'parmenides': -370, 'theaetetus': -369,

    # Aristotle
    'nicomachean ethics': -350, 'eudemian ethics': -350,
    'politics': -350, 'rhetoric': -350,
    'on the soul': -350, 'poetics': -335,

    # Stoic / late antique
    'meditations': 170,  # Marcus Aurelius
    'enchiridion': 125,  # Epictetus
    'parallel lives': 100, 'lives of the noble greeks and romans': 100,
    'the consolation of philosophy': 524,

    # East Asian / South Asian
    'the analects': -500, 'analects': -500, 'analects of confucius': -500,
    'tao te ching': -400,
    'art of war': -500, 'the art of war': -500,
    'mahabharata': -400,
    'ramayana': -400,
    'the bhagavad gita': -400, 'bhagavad gita': -400,
    'the dhammapada': -250, 'dhammapada': -250,

    # Mesopotamian
    'epic of gilgamesh': -2100, 'the epic of gilgamesh': -2100,

    # Medieval
    'beowulf': 1000,
    'the divine comedy': 1320, 'divine comedy': 1320,
    'inferno': 1320,
    'the canterbury tales': 1387, 'canterbury tales': 1387,
}

# Tolerance: skip the patch if the existing year is already within this
# many years of the canonical (some books have correct values from
# manual curation).
TOLERANCE = 50


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    fixed: list[tuple[str, int, int]] = []
    skipped_close: list[tuple[str, int, int]] = []
    not_found: list[str] = []

    for f in sorted(BOOKS_DIR.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        title = d["title"].lower().strip()
        canonical = ANCIENT_WORKS.get(title)
        if canonical is None:
            continue
        existing = d.get("first_published")
        if existing is None:
            not_found.append(d["slug"])
            existing = 99999
        if abs(existing - canonical) <= TOLERANCE:
            skipped_close.append((d["slug"], existing, canonical))
            continue

        fixed.append((d["slug"], existing, canonical))

        if args.apply:
            d["first_published"] = canonical
            d.pop("first_published_circa", None)  # canonical years aren't circa
            prov = d.setdefault("_provenance", {})
            prov["first_published"] = "manual"
            save_json(f, d)

    print(f"Patched: {len(fixed)} books")
    for slug, old, new in fixed:
        print(f"  {slug}: {old} → {new}")
    if skipped_close:
        print(f"\nAlready close (within {TOLERANCE}y): {len(skipped_close)}")
    if not args.apply:
        print("\nDry-run — pass --apply to write")
    return 0


if __name__ == "__main__":
    sys.exit(main())
