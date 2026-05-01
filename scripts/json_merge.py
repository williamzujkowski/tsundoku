"""Additive-merge helpers shared by book and author enrichment.

The invariant: once a field has a non-empty value, no enrichment run will
silently wipe or overwrite it. New values can only fill empty fields.
"""

import json
from pathlib import Path


EMPTY_SENTINELS = (None, "", [], {})


def is_empty(value) -> bool:
    """Treat None, empty string, empty list, and empty dict as empty."""
    return value in EMPTY_SENTINELS or value == [] or value == {}


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
