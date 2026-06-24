"""Unit tests for split_authors() in generate-author-stubs.py.

split_authors() (Python) and parseAuthors() (TypeScript, src/utils/formatting.ts)
are TWO parallel implementations of the same byline-splitting rule. They MUST
agree, or author-page links (TS) and author stubs / book_count (Python) diverge,
producing 404s or orphaned records.

PARITY_CASES below is the shared contract. The mirror test in
src/utils/formatting.test.ts ("#198 parity contract") asserts parseAuthors()
produces the SAME `parts` for every byline here — keep the two lists in sync.
"""

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "generate_author_stubs", Path(__file__).parent / "generate-author-stubs.py"
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
split_authors = _mod.split_authors


# byline -> expected component parts. Shared, verbatim, with the TS mirror.
PARITY_CASES: dict[str, list[str]] = {
    # --- simple / pre-existing behavior (must not regress) ---
    "Plato": ["Plato"],
    "Robert Jordan & Brandon Sanderson": ["Robert Jordan", "Brandon Sanderson"],
    "Brian W. Kernighan and Rob Pike": ["Brian W. Kernighan", "Rob Pike"],
    "Niccolò Machiavelli, Stephen Brennan": ["Niccolò Machiavelli", "Stephen Brennan"],
    "A.A. Milne": ["A.A. Milne"],
    "Karl Marx and Friedrich Engels": ["Karl Marx", "Friedrich Engels"],
    "Abraham Silberschatz, Peter Galvin, Greg Gagne": [
        "Abraham Silberschatz",
        "Peter Galvin",
        "Greg Gagne",
    ],
    "Marx & Engels": ["Marx", "Engels"],
    "Smith, John": ["Smith, John"],
    # org PREFIX + real people still splits (org-suffix in name, no slash)
    "Calm Publications Staff, Kevin Crane, Carolyn Thomson, Peter Dans": [
        "Calm Publications Staff",
        "Kevin Crane",
        "Carolyn Thomson",
        "Peter Dans",
    ],
    # single-token last-name list stays intact (no 2-token evidence);
    # trailing comma stripped (#210)
    "Aho, Lam, Sethi, and Ullman": ["Aho, Lam, Sethi", "Ullman"],
    # --- #198 regressions: mixed comma + and/& + slash ---
    "Alexander Hamilton, James Madison, and John Jay": [
        "Alexander Hamilton",
        "James Madison",
        "John Jay",
    ],
    "Robin Asbell, Susie Middleton, Karen Morgan, Joseph Shuldiner, "
    "Melissa's / World Variety Produce, Inc.": [
        "Robin Asbell",
        "Susie Middleton",
        "Karen Morgan",
        "Joseph Shuldiner",
        "Melissa's",
        "World Variety Produce, Inc.",  # org suffix stays attached
    ],
    # purely institutional byline stays one entity (the `and`s are inside
    # division names, not author boundaries)
    "National Research Council, Division on Earth and Life Studies, "
    "Commission on Geosciences, Environment and Resources, "
    "Committee on Grand Canyon Monitoring and Research": [
        "National Research Council, Division on Earth and Life Studies, "
        "Commission on Geosciences, Environment and Resources, "
        "Committee on Grand Canyon Monitoring and Research"
    ],
    # slash inside parentheses is part of the name, not a separator
    "Various (Arabic/Persian)": ["Various (Arabic/Persian)"],
}


@pytest.mark.parametrize("byline,expected", PARITY_CASES.items())
def test_split_authors_parity_cases(byline: str, expected: list[str]) -> None:
    assert split_authors(byline) == expected


def test_org_suffix_comma_kept_attached() -> None:
    # A corporate suffix after a comma is part of the org name, never a separate
    # author — even when the byline is split on other separators.
    assert split_authors("Jane Roe / Acme Corp, Inc.") == ["Jane Roe", "Acme Corp, Inc."]


def test_three_authors_with_trailing_and() -> None:
    assert split_authors("Ann Lee, Bob Fox, and Cy Ng") == ["Ann Lee", "Bob Fox", "Cy Ng"]
