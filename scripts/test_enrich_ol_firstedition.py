"""Fixture-based tests for the first-edition enricher's pure functions.

These guard the heuristics against regressions when MAX_MATCHING_FOR_TRUST,
the consensus filter, or the picker ranking get tuned. Each fixture
captures a real-world edge case identified during PR #125 review.

The functions under test are pure given a list of synthetic edition dicts,
so we don't hit the network — these tests run in milliseconds.
"""

import importlib.util
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

# The module name has hyphens, so import via spec
_spec = importlib.util.spec_from_file_location(
    "enrich_ol_firstedition",
    Path(__file__).parent / "enrich-ol-firstedition.py",
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

determine_target_year = _mod.determine_target_year
matching_editions = _mod.matching_editions
pick_first_edition = _mod.pick_first_edition
pick_representative_edition = _mod.pick_representative_edition
derive_fields = _mod.derive_fields
edition_year = _mod.edition_year
ISBN_INTRODUCTION_YEAR = _mod.ISBN_INTRODUCTION_YEAR
MAX_MATCHING_FOR_TRUST = _mod.MAX_MATCHING_FOR_TRUST


def E(year=None, *, isbn13=None, isbn10=None, publishers=None, pages=None,
      languages=("eng",), translation=False, contributors=None,
      title="X", key="/books/OLfakeM"):
    """Build a synthetic OL edition dict. Keep the shape close to real OL responses."""
    ed = {"key": key, "title": title}
    if year is not None:
        ed["publish_date"] = str(year)
    if isbn13 is not None:
        ed["isbn_13"] = isbn13 if isinstance(isbn13, list) else [isbn13]
    if isbn10 is not None:
        ed["isbn_10"] = isbn10 if isinstance(isbn10, list) else [isbn10]
    if publishers is not None:
        ed["publishers"] = publishers
    if pages is not None:
        ed["number_of_pages"] = pages
    if languages:
        ed["languages"] = [{"key": f"/languages/{c}"} for c in languages]
    if translation:
        ed["translation_of"] = "Original Title"
        ed["translated_from"] = [{"key": "/languages/jpn"}]
    if contributors:
        ed["contributors"] = contributors
    return ed


class TestDetermineTargetYear:
    def test_keeps_known_year_when_no_earlier_consensus(self):
        eds = [E(2005), E(2006), E(2007), E(2010)]
        assert determine_target_year(eds, known_first_year=2005) == 2005

    def test_adopts_earlier_with_consensus(self):
        # 2 editions agree on 2002 (earlier than known 2005)
        eds = [E(2002), E(2002), E(2005), E(2010)]
        assert determine_target_year(eds, known_first_year=2005) == 2002

    def test_ignores_solo_earlier_year(self):
        # 1 edition claims 1900 (the bogus 1984 Russian case) — not enough
        eds = [E(1900), E(1949), E(1949), E(1949), E(2010)]
        assert determine_target_year(eds, known_first_year=1949) == 1949

    def test_picks_smallest_consensus_year(self):
        eds = [E(1900), E(1900), E(1949), E(1949), E(1949)]
        assert determine_target_year(eds, known_first_year=1949) == 1900

    def test_skips_circa_dates_from_consensus(self):
        # circa dates should not be counted as "precise" votes
        eds = [
            {"publish_date": "ca. 1900"},
            {"publish_date": "ca. 1900"},
            E(1949), E(1949),
        ]
        assert determine_target_year(eds, known_first_year=1949) == 1949

    def test_no_anchor_returns_none(self):
        # User asked: don't derive a year from editions alone — Wikidata fills these
        eds = [E(1725), E(1850), E(1999)]
        assert determine_target_year(eds, known_first_year=None) is None

    def test_no_editions_keeps_known(self):
        assert determine_target_year([], known_first_year=2005) == 2005

    def test_multivolume_close_years(self):
        # LOTR-style: vol 1 in 1954, vol 2 in 1954, vol 3 in 1955
        eds = [E(1954), E(1954), E(1955), E(1955)]
        assert determine_target_year(eds, known_first_year=1954) == 1954


class TestMatchingEditions:
    def test_within_tolerance(self):
        eds = [E(1949), E(1948), E(1950), E(1955)]
        m = matching_editions(eds, target_year=1949)
        assert len(m) == 3

    def test_strict_when_off_by_two(self):
        eds = [E(1949), E(1947), E(1951)]
        m = matching_editions(eds, target_year=1949)
        assert len(m) == 1

    def test_none_target(self):
        assert matching_editions([E(1949)], target_year=None) == []


class TestPickFirstEdition:
    def test_prefers_year_exact(self):
        eds = [E(1948, publishers=["X"]), E(1949, publishers=["Y"])]
        # target=1949, ±1 includes both. Year-exact wins.
        first = pick_first_edition(eds, target_year=1949)
        assert first["publishers"] == ["Y"]

    def test_prefers_non_translation(self):
        # Both year 1949, one is a translation
        eds = [E(1949, translation=True, publishers=["A"]), E(1949, publishers=["B"])]
        first = pick_first_edition(eds, target_year=1949)
        assert first["publishers"] == ["B"]

    def test_prefers_with_publishers(self):
        eds = [E(1949), E(1949, publishers=["B"])]
        first = pick_first_edition(eds, target_year=1949)
        assert first["publishers"] == ["B"]

    def test_returns_none_for_empty_match(self):
        assert pick_first_edition([], target_year=1949) is None


class TestPickRepresentativeEdition:
    def test_matches_book_isbn(self):
        eds = [
            E(2010, isbn13="9999999999999"),
            E(2020, isbn13="9781234567890"),
            E(2015, isbn13="9780000000000"),
        ]
        rep = pick_representative_edition(eds, book_isbn="9781234567890")
        assert rep["isbn_13"] == ["9781234567890"]

    def test_isbn_with_dashes_normalized(self):
        eds = [E(2020, isbn13="9781234567890")]
        rep = pick_representative_edition(eds, book_isbn="978-1-234-56789-0")
        assert rep is not None

    def test_falls_back_to_recent_english_with_isbn(self):
        eds = [
            E(2010, isbn13="A", pages=100),
            E(2020, isbn13="B", pages=200),
            E(2015, isbn13="C", pages=150),
        ]
        rep = pick_representative_edition(eds, book_isbn=None)
        assert rep["isbn_13"] == ["B"]  # most recent

    def test_skips_non_english_when_english_available(self):
        eds = [
            E(2025, isbn13="A", pages=100, languages=("jpn",)),
            E(2020, isbn13="B", pages=200, languages=("eng",)),
        ]
        rep = pick_representative_edition(eds, book_isbn=None)
        assert rep["isbn_13"] == ["B"]


class TestDeriveFields:
    def test_book_with_known_year_corrected(self):
        # Kafka case: book has 2005 (English translation date), editions show
        # consensus on 2002 (Japanese original)
        book = {"first_published": 2005, "title": "Kafka on the Shore"}
        eds = [
            E(2002, languages=("jpn",), title="海辺のカフカ", publishers=["Shinchosha"]),
            E(2002, languages=("jpn",), title="海辺のカフカ", publishers=["Shinchosha"]),
            E(2005, languages=("eng",), translation=True, publishers=["Knopf"], isbn13="9781400079278", pages=467),
        ]
        out = derive_fields(eds, book)
        assert out["first_published"] == 2002
        assert out["original_language"] == "jpn"
        assert out["original_title"] == "海辺のカフカ"
        assert out.get("translator") is None  # rep edition has no contributors

    def test_pre_isbn_book_gets_explicit_null(self):
        # Pride & Prejudice: 1813 is correct, no first-edition ISBN possible
        book = {"first_published": 1813, "title": "Pride and Prejudice"}
        eds = [E(1813), E(1815)]
        out = derive_fields(eds, book)
        assert out["first_published"] == 1813
        assert out["first_edition_isbn"] is None

    def test_post_isbn_low_confidence_skips_isbn(self):
        # Many editions for the year, > MAX_MATCHING_FOR_TRUST → don't trust ISBN
        book = {"first_published": 1990, "title": "X"}
        eds = [E(1990, isbn13=f"978000000000{i}") for i in range(10)]
        out = derive_fields(eds, book)
        assert out["first_published"] == 1990
        assert "first_edition_isbn" not in out  # uncertain — leave undefined

    def test_post_isbn_high_confidence_writes_isbn(self):
        # Few editions, > MAX_MATCHING_FOR_TRUST not exceeded → trust the ISBN
        book = {"first_published": 1990, "title": "X"}
        eds = [E(1990, isbn13="9781234567890", publishers=["Real"])]
        out = derive_fields(eds, book)
        assert out["first_edition_isbn"] == "9781234567890"

    def test_no_first_published_when_no_anchor(self):
        # Iliad case: no known year, no editions old enough to trust
        book = {"title": "The Iliad"}
        eds = [E(1725), E(1850), E(1999)]
        out = derive_fields(eds, book)
        assert "first_published" not in out
        assert "first_edition_isbn" not in out  # no target_year to test against
        assert out["editions_count"] == 3
        assert "representative_edition_key" in out

    def test_translator_credit_from_representative(self):
        # Translator only set when rep edition has a Translator contributor
        book = {"first_published": 1949, "isbn": "9781111111111", "title": "X"}
        eds = [
            E(1949, publishers=["Original"]),
            E(2020, isbn13="9781111111111", languages=("eng",), pages=300,
              contributors=[{"role": "Translator", "name": "Jane Doe"}]),
        ]
        out = derive_fields(eds, book)
        assert out.get("translator") == "Jane Doe"

    def test_original_language_only_for_non_english(self):
        # English-original work: don't write original_language=eng
        book = {"first_published": 1949, "title": "X"}
        eds = [E(1949, languages=("eng",), publishers=["Real"], title="X Original")]
        out = derive_fields(eds, book)
        assert "original_language" not in out
        assert "original_title" not in out  # only set for non-English

    def test_empty_editions(self):
        book = {"title": "X"}
        out = derive_fields([], book)
        assert out == {}
