#!/usr/bin/env python3
"""Suggest category changes for books based on tags + subjects.

Many books in "Literature" or "Mystery" are mis-categorized (per #113).
This script walks every book and, when its tags / subjects strongly indicate
a different category that already exists, proposes a move. Only applies
moves with HIGH confidence (single dominant signal, no conflicts).

Usage:
  python scripts/recategorize.py             # dry-run report
  python scripts/recategorize.py --apply     # actually move
  python scripts/recategorize.py --report    # detailed signal stats
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from enrichment_config import BOOKS_DIR
from json_merge import save_json


# High-confidence tag → category mapping. These tags are reliable indicators.
HIGH_CONFIDENCE_TAGS = {
    "poetry": "Poetry",
    "fantasy": "Fantasy",
    "sci-fi": "Science Fiction",
    "science-fiction": "Science Fiction",
    "horror": "Horror",
    "memoir": "Biography/Memoir",
    "computer-science": "Computer Science",
    "programming": "Computer Science",
    "security": "Security",
    "cryptography": "Security",
}

# Tags that need subject corroboration to avoid false positives:
# e.g., "mystery", "drama", "biography", "politics", "philosophy"
NEEDS_SUBJECT_TAGS = {
    "mystery": "Mystery",
    "detective": "Mystery",
    "crime": "Mystery",
    "drama": "Drama",
    "play": "Drama",
    "plays": "Drama",
    "biography": "Biography/Memoir",
    "autobiography": "Biography/Memoir",
    "politics": "Political Theory",
    "political-theory": "Political Theory",
    "philosophy": "Philosophy",
}

# Subjects from Open Library (LCSH) — must contain one of these phrases.
# Subjects are typically curated, so they provide high-fidelity corroboration.
SUBJECT_KEYWORDS = {
    "Poetry": ["poetry", "verse", "poems", "sonnets", "ballads", "poetic works"],
    "Drama": [
        "drama (dramatic works by one author)",
        "plays (theater)",
        "tragedies",
        "comedies",
        "theatre",
        "english drama",
        "american drama",
        "french drama",
        "greek drama",
        "one-act plays",
        "historical drama",
        "dramatic works",
        "theatrical productions",
    ],
    "Mystery": [
        "detective and mystery",
        "detective stories",
        "mystery fiction",
        "crime fiction",
        "whodunit",
        "police procedural",
        "private investigators",
        "murder -- fiction",
        "mystery and detective stories",
    ],
    "Fantasy": [
        "fantasy fiction",
        "epic fantasy",
        "magic in fiction",
        "wizards in fiction",
        "dragons in fiction",
        "high fantasy",
        "urban fantasy",
        "sword and sorcery",
        "imaginary places",
        "elves in fiction",
    ],
    "Science Fiction": [
        "science fiction",
        "space warfare",
        "interplanetary voyages",
        "dystopias",
        "cyberpunk",
        "time travel in fiction",
        "artificial intelligence -- fiction",
        "alien civilizations",
        "space colonies",
        "life on other planets",
    ],
    "Horror": [
        "horror fiction",
        "ghost stories",
        "gothic fiction",
        "vampires",
        "supernatural in fiction",
        "haunted houses in fiction",
        "horror tales",
    ],
    "Biography/Memoir": [
        "biography",
        "memoir",
        "autobiography",
        "diaries",
        "personal narratives",
    ],
    "Philosophy": [
        "philosophy",
        "ethics",
        "metaphysics",
        "epistemology",
        "logic",
        "existentialism",
        "political philosophy",
        "phenomenology",
    ],
    "Computer Science": [
        "computer programming",
        "algorithms",
        "data structures",
        "software engineering",
        "operating systems (computers)",
        "computer networks",
        "programming languages (electronic computers)",
    ],
    "Security": [
        "cryptography",
        "computer security",
        "data encryption",
        "network security",
        "cybersecurity",
        "ciphers",
    ],
    "Political Theory": [
        "political science",
        "political theory",
        "totalitarianism",
        "democracy",
        "socialism",
        "anarchism",
        "state, the",
    ],
}

SCI_FI_KEYWORDS = [
    "space", "alien", "starship", "galaxy", "future", "robot", "cyberpunk",
    "time travel", "interplanetary", "dystopia", "artificial intelligence",
]
FANTASY_KEYWORDS = [
    "magic", "wizard", "dragon", "spell", "witch", "sorcery", "elf",
    "kingdom", "mythical", "epic fantasy", "faerie", "quest",
]


def existing_categories() -> set[str]:
    """Discover what categories actually exist in the data, lower-cased for matching."""
    cats = set()
    for f in BOOKS_DIR.glob("*.json"):
        d = json.loads(f.read_text())
        cats.add(d.get("category", ""))
    return cats


def _keyword_matches(keyword: str, text: str) -> bool:
    """Check if keyword matches in text, using word boundaries for single words."""
    if " " not in keyword and "-" not in keyword:
        return bool(_re.search(r"\b" + _re.escape(keyword) + r"\b", text))
    return keyword in text


def _subject_match(subjects: list[str], keywords: list[str]) -> bool:
    return any(any(_keyword_matches(k, sub) for k in keywords) for sub in subjects)


# --- Library classification → category mapping ----------------------------
#
# DDC (Dewey Decimal) and LCC (Library of Congress) are professional library
# classification systems and are far more reliable signals than free-text tags
# or subjects. When a book has DDC/LCC in its OL data, we can suggest a
# category with high confidence.
#
# Mappings cover the common cases. Anything not matched falls through to the
# tag/subject heuristics above.

import re as _re


def category_from_ddc(ddc_list: list[str]) -> str | None:
    """Best-guess category from a DDC array. Returns None if no clean match."""
    if not ddc_list:
        return None
    # Special case: 822.33 is William Shakespeare
    for raw in ddc_list:
        if raw and "822.33" in raw:
            return "Drama"
    # Take the first numeric DDC and parse the integer prefix (3 digits).
    for raw in ddc_list:
        m = _re.match(r"(\d{3})", raw or "")
        if not m:
            continue
        n = int(m.group(1))
        # Literature subdivisions — prefer specific over generic
        if 800 <= n <= 899:
            # 808/809 = literary criticism / general literature
            if n in (808, 809):
                return "Literary Criticism"
            # X11/X21/X31/X41/X51/X61/X71/X81 = Poetry (last digit 1)
            # X12/X22/.../X82 = Drama (last digit 2)
            # X13/X23/.../X83 = Fiction (last digit 3)
            ones = n % 10
            if ones == 1:
                return "Poetry"
            if ones == 2:
                return "Drama"
            return "Literature"  # fiction or other
        if 100 <= n <= 199:
            return "Philosophy"
        if 200 <= n <= 299:
            return "Religion"
        if 320 <= n <= 329:
            return "Political Theory"
        if 330 <= n <= 339:
            return "Economics"
        if 510 <= n <= 519:
            return "Mathematics"
        if 520 <= n <= 599:
            return "Science"
        if 900 <= n <= 999:
            if n == 920:
                return "Biography/Memoir"
            return "History"
        if n < 100:  # 0XX = computing / information
            if "005.8" in (raw or ""):
                return "Security"
            return "Computer Science"
    return None


def category_from_lcc(lcc_list: list[str]) -> str | None:
    """Best-guess category from an LCC array. Uses the class letter prefix."""
    if not lcc_list:
        return None
    for raw in lcc_list:
        s = (raw or "").strip().upper()
        if not s or not s[0].isalpha():
            continue
        # 2-char prefix (most LCC subclasses are 2 letters)
        c1 = s[0]
        c2 = s[:2]

        if c2 in ("PR", "PS", "PT", "PQ", "PB", "PC", "PD", "PE", "PF", "PG", "PH", "PJ", "PK", "PL", "PM", "PZ"):
            return "Literature"
        if c2 == "PA":
            return "Classics"
        if c2 == "PN":
            return "Literary Criticism"
        if c1 in ("D", "E", "F"):
            return "History"
        # Religion: BL/BM/BP/BQ/BR/BS/BT/BV/BX. Plain B = philosophy.
        if c2 in ("BL", "BM", "BP", "BQ", "BR", "BS", "BT", "BV", "BX"):
            return "Religion"
        if c1 == "B":
            return "Philosophy"
        if c2 == "QA":
            # QA76 = Computer Science; rest of QA = Mathematics
            if s.startswith(("QA76", "QA-76", "QA 76")):
                return "Computer Science"
            return "Mathematics"
        if c2 in ("QB", "QC", "QD", "QE", "QH", "QK", "QL", "QM", "QP", "QR"):
            return "Science"
        if c1 == "Q":
            return "Science"
        if c2 == "TK":
            return "Computer Science"
        if c2 in ("HB", "HC", "HD", "HE", "HF", "HG", "HJ"):
            return "Economics"
        if c1 == "J":
            return "Political Theory"
    return None


def category_from_classification(book: dict, existing: set[str]) -> str | None:
    """Combine DDC + LCC into a single suggestion.

    Per the user's "use DDC/LCC as authoritative" directive:
      * DDC and LCC agree, or only one is present → that's the proposal.
      * DDC and LCC disagree → bail (don't guess).
      * Trust the classification. National-literature LCC classes (PR, PS, ...)
        will pull genre fiction toward "Literature" because libraries don't
        distinguish genre. That's how libraries work; users still filter by
        genre tags. The site's own tag filter on /browse/ keeps that surface.
    """
    ddc_cat = category_from_ddc(book.get("ddc") or [])
    lcc_cat = category_from_lcc(book.get("lcc") or [])
    current = book.get("category", "")

    if ddc_cat and ddc_cat in existing and ddc_cat != current:
        if lcc_cat and lcc_cat != ddc_cat and lcc_cat in existing:
            return None  # disagree
        return ddc_cat
    if lcc_cat and lcc_cat in existing and lcc_cat != current:
        return lcc_cat
    return None


def proposed_category(book: dict, existing: set[str]) -> str | None:
    """Return the target category if there's a single strong signal; None otherwise.

    Conservative — only proposes a move when:
      1. The book has a high-confidence tag (poetry, fantasy, sci-fi, etc.),
         AND no conflicting high-confidence tag pointing somewhere else, OR
      2. The book has a low-confidence tag (drama, biography, etc.) AND an
         Open Library subject also points to the same category, OR
      3. Two or more Open Library subjects agree on the same category.
    AND the proposal must differ from the current category and exist in the catalog.
    """
    current = book.get("category", "")
    tags = set(book.get("tags") or [])
    subjects = [s.lower() for s in (book.get("subject_facet") or [])]
    desc = (book.get("description") or "").lower()

    # Step 1 — collect candidates with confidence scores
    candidates: Counter[str] = Counter()

    # Curated category inertia: non-Literature categories have strong baseline
    # inertia (+12) so established books (especially Classics, History, Philosophy)
    # aren't casually bounced around.
    if current and current != "Literature":
        candidates[current] += 12

    # High-confidence tag signal — weight 5
    for tag in tags:
        target = HIGH_CONFIDENCE_TAGS.get(tag)
        if target and target in existing:
            candidates[target] += 5

    # Low-confidence tag — only counts if subject also matches
    for tag in tags:
        target = NEEDS_SUBJECT_TAGS.get(tag)
        if not target or target not in existing:
            continue
        if _subject_match(subjects, SUBJECT_KEYWORDS.get(target, [])):
            candidates[target] += 5  # tag + subject = strong

    # Subject-only signal — weight 4 if at least 2 subjects match
    for cat, keywords in SUBJECT_KEYWORDS.items():
        if cat not in existing:
            continue
        match_count = sum(
            1 for sub in subjects if any(_keyword_matches(k, sub) for k in keywords)
        )
        if match_count >= 2:
            candidates[cat] += 4

    # DDC classification signal (weight 3)
    ddc_cat = category_from_ddc(book.get("ddc") or [])
    if ddc_cat and ddc_cat in existing:
        candidates[ddc_cat] += 3

    # Non-fiction & Drama safeguards:
    # If a book has "fictional works by one author" (LCSH standard for novels),
    # it must NOT be moved into non-fiction shelves (Philosophy, Political Theory, Security)
    # or into Drama (unless explicitly tagged play/plays or Shakespeare DDC 822.33).
    has_fictional_works = any("fictional works by one author" in s for s in subjects)
    if has_fictional_works:
        candidates["Philosophy"] = 0
        candidates["Political Theory"] = 0
        candidates["Security"] = 0
        has_play_tag = bool({"play", "plays"} & tags)
        is_shakespeare = any("822.33" in str(d) for d in (book.get("ddc") or []))
        if not has_play_tag and not is_shakespeare:
            candidates["Drama"] = 0

    # Horror safeguard: Christmas/festive stories, casual ghost stories, or satire
    # (e.g. Northanger Abbey) shouldn't become Horror unless explicitly tagged horror.
    if candidates["Horror"] > 0 and "horror" not in tags:
        has_satire_or_parody = any(any(_keyword_matches(k, s) for k in ["satire", "parody"]) for s in subjects)
        has_real_horror_subject = any(
            any(_keyword_matches(k, s) for k in ["horror fiction", "gothic fiction", "vampires", "horror tales"])
            for s in subjects
        )
        if has_satire_or_parody or not has_real_horror_subject:
            candidates["Horror"] = 0

    # Poetry safeguard: prose short story collections or novels must not move to Poetry
    # unless explicitly tagged poetry.
    if candidates["Poetry"] > 0 and "poetry" not in tags:
        has_prose_signal = bool({"short-stories"} & tags) or any(
            any(_keyword_matches(k, s) for k in ["short stories", "fictional works by one author"])
            for s in subjects
        )
        if has_prose_signal:
            candidates["Poetry"] = 0

    # Speculative fiction tie-breaker between Science Fiction and Fantasy
    if candidates["Science Fiction"] > 0 and candidates["Fantasy"] > 0 and candidates["Science Fiction"] == candidates["Fantasy"]:
        scifi_matches = sum(1 for s in subjects if any(k in s for k in SCI_FI_KEYWORDS)) + sum(1 for k in SCI_FI_KEYWORDS if k in desc)
        fantasy_matches = sum(1 for s in subjects if any(k in s for k in FANTASY_KEYWORDS)) + sum(1 for k in FANTASY_KEYWORDS if k in desc)
        if scifi_matches > fantasy_matches:
            candidates["Science Fiction"] += 1
        elif fantasy_matches > scifi_matches:
            candidates["Fantasy"] += 1

    if not candidates:
        return None

    most_common = candidates.most_common(2)
    top_cat, top_score = most_common[0]
    runner_up_score = most_common[1][1] if len(most_common) > 1 else 0

    # Need 4+ to commit
    if top_score < 4:
        return None
    if runner_up_score >= top_score:
        return None  # tied
    if top_cat == current:
        return None
    return top_cat


def main() -> int:
    parser = argparse.ArgumentParser(description="Re-categorize books based on tags + subjects + DDC/LCC")
    parser.add_argument("--apply", action="store_true", help="Actually write changes")
    parser.add_argument("--report", action="store_true", help="Print detailed per-category counts")
    parser.add_argument(
        "--from-category",
        type=str,
        default=None,
        help="Only consider books currently in this category (e.g. 'Literature')",
    )
    parser.add_argument(
        "--use-classification",
        action="store_true",
        help="Use Open Library DDC/LCC classification as the primary signal (most reliable). "
             "Falls back to tag/subject heuristic.",
    )
    args = parser.parse_args()

    existing = existing_categories()
    moves: list[tuple[Path, dict, str]] = []  # (path, book, target_cat)

    for path in sorted(BOOKS_DIR.glob("*.json")):
        book = json.loads(path.read_text())
        if args.from_category and book.get("category") != args.from_category:
            continue
        target = None
        if args.use_classification:
            target = category_from_classification(book, existing)
        if not target:
            target = proposed_category(book, existing)
        if target:
            moves.append((path, book, target))

    print(f"Proposed re-categorizations: {len(moves)}")
    by_move = Counter()
    for _, book, target in moves:
        by_move[(book.get("category"), target)] += 1
    for (frm, to), count in by_move.most_common():
        print(f"  {count:4d}  {frm!r:30s} → {to!r}")

    if args.report:
        print("\nSample books per move:")
        for (frm, to), _ in by_move.most_common():
            print(f"\n  {frm} → {to}:")
            samples = [b for _, b, t in moves if t == to and b.get("category") == frm][:5]
            for b in samples:
                tags = ", ".join((b.get("tags") or [])[:3])
                print(f"    [{b.get('priority', '?')}]  {b['title']} (tags: {tags})")

    if args.apply:
        for path, book, target in moves:
            book["category"] = target
            save_json(path, book)
        print(f"\nApplied {len(moves)} category changes.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
