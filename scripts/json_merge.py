"""Additive-merge helpers shared by book and author enrichment.

Two merge modes are supported:

1. additive_merge — never overwrites a non-empty field. Used when an
   enricher has no way to know whether existing data is curated.

2. provenance_merge — overwrites only when the incoming source has a
   strictly higher rank than the existing field's recorded provenance.
   The book record carries a `_provenance` dict mapping field → source-tag.
   Fields without recorded provenance default to rank 0 (legacy/unknown),
   so any tagged source can correct them. Manual edits should be marked
   with provenance "manual" to lock them in.

The provenance ranks live below in SOURCE_RANK. Add new sources there
when you write a new enricher. Higher number = more authoritative.
"""

import json
from pathlib import Path
from typing import Iterable


EMPTY_SENTINELS = (None, "", [], {})

# Source ranks for provenance_merge. Higher = more trusted.
# Existing records without a `_provenance` entry default to rank 0,
# so any tagged source above 0 can correct them on the next pass.
SOURCE_RANK = {
    # User-curated values are immutable. Set this provenance manually when
    # editing a book record by hand.
    "manual": 100,

    # Wikidata via the strong P648 (Open Library ID) cross-link. Only one
    # match per ISBN/OL key, so collisions are vanishingly rare.
    "wikidata_v1": 85,

    # Open Library editions consensus — see scripts/enrich-ol-firstedition.py.
    # Authoritative for first-publication year + first_edition_isbn for
    # works whose first edition is post-1800 and well-cataloged.
    "ol_firstedition_v1": 80,

    # Wikidata via fuzzy title+author search (future scripts/enrich-wikidata-
    # fallback.py). Strong enough to fill blanks but never override anything
    # tagged — match noise is unavoidable.
    "wikidata_search_v1": 50,

    # Open Library work-level data from search.json — see
    # scripts/enrich-ol-classification.py. DDC, LCC, subject_facet, ISBN.
    "ol_classification_v2": 60,

    # Open Library data from the original enrich.py monolithic pass.
    # Mostly superseded but kept for provenance-trail completeness.
    "ol_search_v1": 40,

    # Google Books — descriptions and ISBNs. Less authoritative than OL for
    # publication metadata, treated as a fallback signal only.
    "google_books_v1": 35,

    # Wikipedia REST API — author bio, photo. Bio text is third-party-edited
    # so we keep it lower than structured-KB sources.
    "wikipedia_v1": 30,

    # Coarse derivation from existing fields — e.g., reverse-mapping the
    # `category` bucket to a baseline DDC/LCC for records where every
    # external source has nothing. Intentionally low so any real
    # classification source (manual, ol_classification_v2, wikidata_v1)
    # overwrites when fields_overwritable includes the relevant key.
    "derived_v1": 5,

    # Anything in book/author records before provenance was tracked. Any
    # tagged source can correct these.
    "legacy": 0,
}


def is_empty(value) -> bool:
    """Treat None, empty string, empty list, and empty dict as empty.

    Note: explicit `None` for `first_edition_isbn` is meaningful (pre-ISBN
    works) and the caller can detect by checking the key's presence — this
    helper only reports emptiness in the value sense."""
    if value is None:
        return True
    if isinstance(value, (str, list, dict)) and len(value) == 0:
        return True
    return False


def _rank(source: str | None) -> int:
    if source is None:
        return SOURCE_RANK["legacy"]
    return SOURCE_RANK.get(source, 0)


EXPLICIT_NULL_KEYS = frozenset({"first_edition_isbn"})  # null is meaningful (pre-ISBN works)


def _is_set(book: dict, key: str) -> bool:
    """True iff the field carries information already.

    For most keys, missing or empty means unset. For the keys in
    EXPLICIT_NULL_KEYS, presence-with-None is a meaningful "no it doesn't"
    (e.g. a 17th-century work has no first-edition ISBN, period).
    """
    if key not in book:
        return False
    val = book[key]
    if key in EXPLICIT_NULL_KEYS:
        return True
    return not is_empty(val)


def provenance_merge(
    existing: dict,
    new: dict,
    *,
    source: str,
    fields_overwritable: Iterable[str] = (),
) -> tuple[bool, dict]:
    """Provenance-aware merge.

    For each (key, value) in `new`:
      * if the value is empty (None / "" / [] / {}) it's skipped, EXCEPT that
        an explicit None for keys in EXPLICIT_NULL_KEYS is allowed through
        (those nulls are meaningful — e.g. "this work pre-dates ISBNs").
      * if the existing field is unset, fill it and record provenance.
      * if the field is in `fields_overwritable` AND the incoming source's
        rank exceeds the existing field's recorded provenance rank,
        overwrite and record provenance.
      * else preserve existing.

    `source` may be any string; ranks not in SOURCE_RANK default to 0,
    so an ad-hoc source can fill blanks but never overwrite anything tagged.

    Returns (changed, audit) where `audit` lists each *overwrite* —
    {field: {"from": old, "to": new, "old_source": str|None, "new_source": str}}.
    Pure fills do not produce audit rows.
    """
    incoming_rank = _rank(source)
    overwritable = frozenset(fields_overwritable)
    prov: dict = existing.setdefault("_provenance", {})
    changed = False
    audit: dict = {}

    for key, val in new.items():
        # Filter incoming empties — but let an explicit None through for
        # keys where None is a meaningful answer.
        if is_empty(val):
            if not (val is None and key in EXPLICIT_NULL_KEYS):
                continue

        old_val = existing.get(key)
        old_set = _is_set(existing, key)
        old_source = prov.get(key)
        old_rank = _rank(old_source)

        if not old_set:
            will_write = True
            is_overwrite = False
        elif key in overwritable and incoming_rank > old_rank:
            will_write = True
            is_overwrite = True
        else:
            will_write = False
            is_overwrite = False

        if not will_write:
            continue

        if is_overwrite and old_val != val:
            audit[key] = {
                "from": old_val,
                "to": val,
                "old_source": old_source,
                "new_source": source,
            }
        existing[key] = val
        prov[key] = source
        changed = True

    if not prov:
        existing.pop("_provenance", None)

    return changed, audit


def additive_merge(existing: dict, new: dict) -> bool:
    """Fill empty/missing fields on `existing` from `new`. Mutates in-place.

    Rules:
      * Empty values in `new` are ignored — never overwrite anything with
        None, "", [], or {}.
      * Non-empty existing values are preserved; never overwritten.

    Returns True if any field was changed.
    """
    changed = False
    for key, val in new.items():
        if is_empty(val):
            continue
        if is_empty(existing.get(key)):
            existing[key] = val
            changed = True
    return changed


def merge_unique_sorted(existing, new) -> list:
    """Combine two iterables into a sorted, deduped list (str only)."""
    return sorted(set(existing or []) | set(new or []))


def save_json(path: Path, data: dict) -> None:
    """Write JSON with consistent formatting (2-space indent, trailing newline)."""
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def load_existing(path: Path) -> dict:
    """Read a JSON file, returning {} if it doesn't exist."""
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
