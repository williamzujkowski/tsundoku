#!/usr/bin/env python3
"""Fuzzy retry pass for books that the basic enricher couldn't classify.

The basic scripts/enrich-ol-classification.py uses ISBN-search first and
falls back to title+author search. That misses cases where:

  1. ISBN search returns the edition record (no DDC/LCC) — the work record
     would have classifications but we never query for it.
  2. ISBN doesn't match any OL record at all (out-of-print editions).
  3. Title+author search returns the wrong book first (e.g. "The Man in the
     Iron Mask" matches a Level 5 ESL textbook before the Dumas).

This script retries with three strategies in order:
  a. Title+author keyword search, score by author-last-name presence
  b. Title-only search, filter by author surname match
  c. Author-only search, find by title similarity in their bibliography

Results are scored: classification present (DDC or LCC) is required;
ties broken by title similarity (token-set overlap) then author name match.

Usage:
  python scripts/enrich-ol-fuzzy-retry.py             # dry-run report
  python scripts/enrich-ol-fuzzy-retry.py --apply
  python scripts/enrich-ol-fuzzy-retry.py --apply --limit 100
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus
from urllib.request import urlopen, Request

sys.path.insert(0, str(Path(__file__).parent))

from enrichment_config import BOOKS_DIR, USER_AGENT
from http_cache import cached_fetch
from json_merge import additive_merge, save_json


REQUEST_TIMEOUT = 15
RATE_LIMIT_S = 0.5

OL_SEARCH = "https://openlibrary.org/search.json"
FIELDS = ",".join([
    "key", "title", "author_name", "isbn",
    "ddc", "lcc", "subject_facet",
    "first_publish_year", "language", "number_of_pages_median",
])


# ---------------------------------------------------------------------------
# Tokenization + similarity
# ---------------------------------------------------------------------------

_STOPWORDS = frozenset({"a", "an", "the", "of", "and", "or", "in", "on", "at", "to", "for"})


def tokens(s: str) -> set[str]:
    s = (s or "").lower()
    s = re.sub(r"[^\w\s]", " ", s)
    return {w for w in s.split() if w and w not in _STOPWORDS}


def title_similarity(query: str, candidate: str) -> float:
    """Jaccard-like score on token sets, 0..1."""
    q, c = tokens(query), tokens(candidate)
    if not q or not c:
        return 0.0
    return len(q & c) / max(len(q | c), 1)


def author_last_names(name: str) -> set[str]:
    """Extract candidate surnames from an author string for matching."""
    out = set()
    for part in re.split(r"\s*(?:&| and | with |/|,)\s*", name or "", flags=re.IGNORECASE):
        words = re.findall(r"[A-Za-zÀ-ÿ]+", part)
        if words:
            out.add(words[-1].lower())
    return out


def author_match_score(query_author: str, candidate_authors: list[str]) -> float:
    """1.0 if any author last-name matches; 0 otherwise."""
    q = author_last_names(query_author)
    if not q:
        return 0.0
    for ca in (candidate_authors or []):
        if author_last_names(ca) & q:
            return 1.0
    return 0.0


# ---------------------------------------------------------------------------
# OL fetching + scoring
# ---------------------------------------------------------------------------

def _fetch(url: str) -> dict | None:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            return json.loads(resp.read())
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None


def _search(*, title: str | None = None, author: str | None = None, limit: int = 5) -> list[dict]:
    parts = []
    if title:
        parts.append(f"title={quote_plus(title)}")
    if author:
        parts.append(f"author={quote_plus(author)}")
    parts.append(f"fields={FIELDS}")
    parts.append(f"limit={limit}")
    url = f"{OL_SEARCH}?{'&'.join(parts)}"
    cache_key = f"ta:{title or ''}|{author or ''}|{limit}"
    data = cached_fetch("open_library_fuzzy", cache_key, lambda: _fetch(url), url=url)
    return (data.get("docs") or []) if data else []


def best_match(book: dict) -> dict | None:
    """Try multiple search strategies, return the best-scoring doc with DDC/LCC."""
    title = book.get("title", "")
    author = book.get("author", "")
    if not title:
        return None

    candidates: list[tuple[float, dict]] = []

    # Strategy A: title+author
    for doc in _search(title=title, author=author, limit=5):
        if not (doc.get("ddc") or doc.get("lcc")):
            continue
        score = (
            title_similarity(title, doc.get("title", "")) * 0.6
            + author_match_score(author, doc.get("author_name") or []) * 0.4
        )
        if score >= 0.5:
            candidates.append((score, doc))

    # Strategy B: title only, filter by author surname
    if not candidates:
        for doc in _search(title=title, limit=5):
            if not (doc.get("ddc") or doc.get("lcc")):
                continue
            am = author_match_score(author, doc.get("author_name") or [])
            if am < 1.0:
                continue
            score = title_similarity(title, doc.get("title", ""))
            if score >= 0.5:
                candidates.append((score, doc))

    # Strategy C: author only, find by title similarity in bibliography
    if not candidates:
        for doc in _search(author=author, limit=10):
            if not (doc.get("ddc") or doc.get("lcc")):
                continue
            score = title_similarity(title, doc.get("title", ""))
            if score >= 0.5:
                candidates.append((score, doc))

    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

def extract_fields(work: dict, current: dict) -> dict:
    out: dict = {}
    if work.get("ddc"):
        out["ddc"] = work["ddc"]
    if work.get("lcc"):
        out["lcc"] = work["lcc"]
    if work.get("subject_facet"):
        out["subject_facet"] = work["subject_facet"]
    if not current.get("first_published") and work.get("first_publish_year"):
        out["first_published"] = int(work["first_publish_year"])
    if not current.get("language"):
        langs = work.get("language") or []
        if langs:
            out["language"] = langs[0]
    if not current.get("pages") and work.get("number_of_pages_median"):
        out["pages"] = work["number_of_pages_median"]
    if not current.get("ol_work_key") and work.get("key"):
        out["ol_work_key"] = work["key"]
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Fuzzy retry for unclassified books")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    candidates: list[tuple[Path, dict]] = []
    for f in sorted(BOOKS_DIR.glob("*.json")):
        b = json.loads(f.read_text(encoding="utf-8"))
        if b.get("ddc") or b.get("lcc"):
            continue
        candidates.append((f, b))

    if args.limit:
        candidates = candidates[: args.limit]

    print(f"Books missing DDC and LCC: {len(candidates)}")

    n_matched = 0
    n_filled = 0
    n_no_match = 0

    for i, (path, book) in enumerate(candidates, 1):
        match = best_match(book)
        time.sleep(RATE_LIMIT_S)

        if not match:
            n_no_match += 1
            continue
        n_matched += 1

        new_fields = extract_fields(match, book)
        if not new_fields:
            continue

        added = ", ".join(sorted(new_fields.keys()))
        print(f"  [{i}/{len(candidates)}] \"{book['title'][:40]}\"  matched → {added}")

        if args.apply:
            additive_merge(book, new_fields)
            save_json(path, book)
        n_filled += 1

        if i % 25 == 0:
            print(f"  ... progress: {n_filled} filled, {n_no_match} no-match")

    print(f"\nDone. {n_matched} matches found, {n_filled} got new fields, {n_no_match} no-match.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
