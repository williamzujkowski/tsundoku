#!/usr/bin/env python3
"""Detect and replace non-English book descriptions.

User reported the Tractatus Logico-Philosophicus had a Spanish synopsis;
audit revealed ~17 affected books across the catalog (Spanish, French,
German, Portuguese, Dutch). The bad descriptions came from earlier
enrichment passes that grabbed whichever language Open Library happened
to return first.

For each affected book this script tries, in order:
  1. Wikipedia REST summary (en.wikipedia.org/api/rest_v1/page/summary)
     by the book's title
  2. Open Library work record's `description` field, BUT only when the
     content looks English (the same heuristic that flagged it)
  3. Google Books volumes?q=isbn:X&langRestrict=en
  4. Otherwise: blank the description and tag with provenance `manual`
     so future enrichers don't re-clobber it

Usage:
  python scripts/fix-non-english-descriptions.py             # dry-run
  python scripts/fix-non-english-descriptions.py --apply     # write
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen, Request

sys.path.insert(0, str(Path(__file__).parent))

from enrichment_config import BOOKS_DIR, USER_AGENT
from json_merge import save_json


REQUEST_TIMEOUT = 15
RATE_LIMIT_S = 0.5

# Language-detection heuristics — borrowed from the audit script. The
# threshold is conservative: only mark non-English when the foreign-
# language word count clearly dominates.
ENGLISH = re.compile(
    r"\b(the|of|and|to|a|in|is|that|for|with|as|on|by|are|this|was|be|from|or|an|its|it|but|not|have|has|all|will|one|book|author|published|writes|writing|edition|story|novel|work|english|chapter|first|second|when|where|while|after|before)\b",
    re.IGNORECASE,
)
NON_ENGLISH = re.compile(
    # Spanish + French + German + Portuguese + Dutch markers — anything
    # that's not English-looking.
    r"\b(el|la|los|las|de|que|en|es|son|para|por|del|al|una|uno|más|fue|obra|escribió|según|también|durante|cuando|donde|aquí|allí|nuestro|vida|le|les|des|et|ou|qui|où|dans|avec|sans|cette|ces|était|d'un|d'une|n'est|qu'il|der|die|das|den|dem|ein|eine|einer|und|oder|aber|nicht|mit|von|für|sich|werden|wurde|haben|hatte|sein|seine|als|você|não|ela|isto|aquele|aquela|estão|hij|zij|niet|maar|over|onder|tussen|alleen)\b",
    re.IGNORECASE,
)


def is_non_english(text: str) -> bool:
    if not text:
        return False
    en = len(ENGLISH.findall(text))
    other = len(NON_ENGLISH.findall(text))
    word_count = len(text.split())
    if word_count < 8:
        return False
    return other > en * 1.4 and other >= 4


def is_english(text: str) -> bool:
    if not text:
        return False
    en = len(ENGLISH.findall(text))
    other = len(NON_ENGLISH.findall(text))
    return en > other and en >= 3


def _fetch_json(url: str) -> dict | None:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            return json.loads(resp.read())
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None


def _truncate(text: str, max_chars: int = 500) -> str:
    text = re.sub(r"<[^>]+>", "", text or "").strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rfind(". ")
    return text[: cut + 1] if cut > 200 else text[:max_chars]


def from_wikipedia(title: str) -> str | None:
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(title)}"
    data = _fetch_json(url)
    if not data:
        return None
    extract = data.get("extract") or ""
    if extract and is_english(extract):
        return _truncate(extract)
    return None


def from_ol_work(work_key: str) -> str | None:
    if not work_key:
        return None
    if not work_key.startswith("/works/"):
        return None
    url = f"https://openlibrary.org{work_key}.json"
    data = _fetch_json(url)
    if not data:
        return None
    desc = data.get("description")
    if isinstance(desc, dict):
        desc = desc.get("value", "")
    if not isinstance(desc, str):
        return None
    if is_english(desc):
        return _truncate(desc)
    return None


def from_google_isbn(isbn: str) -> str | None:
    if not isbn:
        return None
    url = (
        f"https://www.googleapis.com/books/v1/volumes"
        f"?q=isbn:{quote(isbn)}&langRestrict=en&maxResults=1"
    )
    data = _fetch_json(url)
    if not data:
        return None
    items = data.get("items") or []
    if not items:
        return None
    desc = (items[0].get("volumeInfo") or {}).get("description") or ""
    if is_english(desc):
        return _truncate(desc)
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    affected = []
    for f in sorted(BOOKS_DIR.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        if is_non_english(d.get("description", "")):
            affected.append((f, d))

    print(f"Found {len(affected)} books with non-English descriptions")

    fixed = 0
    blanked = 0
    for path, book in affected:
        new_desc: str | None = None

        # Try sources in order
        for source_name, fetch in (
            ("wikipedia", lambda: from_wikipedia(book["title"])),
            ("ol_work", lambda: from_ol_work(book.get("ol_work_key", ""))),
            ("google_isbn", lambda: from_google_isbn(book.get("isbn", ""))),
        ):
            new_desc = fetch()
            time.sleep(RATE_LIMIT_S)
            if new_desc:
                action = f"{source_name}"
                break
        else:
            action = "blanked"

        title = book["title"][:50]
        if new_desc:
            print(f"  ✓ [{action:12s}] {title}")
            if args.apply:
                book["description"] = new_desc
                # Tag provenance so the description doesn't get clobbered again
                prov = book.setdefault("_provenance", {})
                prov["description"] = f"fix_non_english_v1_{action}"
                save_json(path, book)
                fixed += 1
        else:
            print(f"  ✗ [blanked    ] {title}")
            if args.apply:
                book.pop("description", None)
                prov = book.setdefault("_provenance", {})
                prov["description"] = "fix_non_english_v1_blanked"
                save_json(path, book)
                blanked += 1

    print(f"\nDone. {fixed} replaced, {blanked} blanked.")
    if not args.apply:
        print("Dry-run — pass --apply to write")

    return 0


if __name__ == "__main__":
    sys.exit(main())
