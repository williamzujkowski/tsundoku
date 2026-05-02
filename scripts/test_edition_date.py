"""Tests for the OL edition-date parser. Real-world strings drawn from
sample OL responses to make sure the parser handles the messy cases we'll
actually encounter."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from edition_date import parse_publish_date, earliest_year


class TestStandardYears:
    def test_plain_4digit(self):
        assert parse_publish_date("1719") == (1719, False)

    def test_year_in_full_date(self):
        assert parse_publish_date("January 1719") == (1719, False)
        assert parse_publish_date("June 24, 1949") == (1949, False)
        assert parse_publish_date("1949-06-08") == (1949, False)

    def test_year_with_parenthetical(self):
        # "1949 (revised 1956)" → take the first
        assert parse_publish_date("1949 (revised 1956)") == (1949, False)

    def test_year_range(self):
        # First year in the range wins
        assert parse_publish_date("1812-1813") == (1812, False)


class TestCirca:
    def test_circa_lowercase(self):
        assert parse_publish_date("ca. 1850") == (1850, True)
        assert parse_publish_date("c. 1850") == (1850, True)
        assert parse_publish_date("circa 1850") == (1850, True)

    def test_question_mark(self):
        assert parse_publish_date("1719?") == (1719, True)

    def test_brackets_with_question(self):
        # "[1719?]" — both bracket-inference and question = circa
        assert parse_publish_date("[1719?]") == (1719, True)

    def test_brackets_without_question_are_certain(self):
        # "[1719]" → bracket without ? is inferred but solid (catalogers' note)
        assert parse_publish_date("[1719]") == (1719, False)


class TestApproximate:
    def test_decade_approx(self):
        assert parse_publish_date("19--") == (1900, True)
        assert parse_publish_date("18uu") == (1800, True)

    def test_century_only(self):
        assert parse_publish_date("19th century") == (1800, True)
        # 19th century → 1800s
        assert parse_publish_date("20th century") == (1900, True)

    def test_n_d(self):
        assert parse_publish_date("n.d.") == (None, True)
        assert parse_publish_date("no date") == (None, True)

    def test_unknown(self):
        assert parse_publish_date("Unknown") == (None, True)


class TestBCE:
    def test_bc_suffix(self):
        assert parse_publish_date("100 BC") == (-100, False)

    def test_bce_suffix(self):
        assert parse_publish_date("428 BCE") == (-428, False)

    def test_bc_lowercase(self):
        assert parse_publish_date("428 bce") == (-428, False)


class TestEmpty:
    def test_none(self):
        assert parse_publish_date(None) == (None, False)

    def test_empty(self):
        assert parse_publish_date("") == (None, False)

    def test_whitespace(self):
        assert parse_publish_date("   ") == (None, False)


class TestRomanNumerals:
    def test_basic(self):
        # MDCCXIX = 1719
        assert parse_publish_date("MDCCXIX") == (1719, False)

    def test_with_circa(self):
        assert parse_publish_date("ca. MDCCXIX") == (1719, True)

    def test_unreasonable_roman_ignored(self):
        # "I" alone shouldn't match as year 1
        result = parse_publish_date("I")
        assert result[0] is None or result[0] >= 100


class TestEarliestYear:
    def test_picks_smallest(self):
        dates = ["2010", "1949", "1984", None, "1720"]
        assert earliest_year(dates) == (1720, False)

    def test_circa_propagates(self):
        # If the earliest is circa, result is circa
        assert earliest_year(["ca. 1719", "1815"]) == (1719, True)

    def test_skip_unparseable(self):
        assert earliest_year(["Unknown", None, "", "1949"]) == (1949, False)

    def test_all_unparseable(self):
        assert earliest_year(["Unknown", None]) == (None, False)

    def test_empty_list(self):
        assert earliest_year([]) == (None, False)

    def test_bce_smallest(self):
        # -428 (Plato) should be earlier than 1900
        assert earliest_year(["1900", "428 BCE", "1500"]) == (-428, False)
