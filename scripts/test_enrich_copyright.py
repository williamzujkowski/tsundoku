"""Tests for compute_copyright_status in enrich-copyright.py.

Locks down the rule precedence (platform > HathiTrust rights > year),
which decides the public-domain / copyright badge on every book page.
"""

import importlib.util
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(__file__))

_spec = importlib.util.spec_from_file_location(
    "enrich_copyright", Path(__file__).parent / "enrich-copyright.py"
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
compute_copyright_status = _mod.compute_copyright_status

VALID = {"public_domain", "likely_public_domain", "in_copyright", "undetermined"}


class TestPlatformSignals:
    def test_gutenberg_is_public_domain(self):
        assert compute_copyright_status({"gutenberg_url": "https://g/1"}) == "public_domain"

    def test_librivox_is_public_domain(self):
        assert compute_copyright_status({"librivox_url": "https://l/1"}) == "public_domain"

    def test_platform_wins_over_recent_year(self):
        # A Gutenberg edition guarantees PD even if a (wrong) modern year is set.
        book = {"gutenberg_url": "https://g/1", "first_published": 2010}
        assert compute_copyright_status(book) == "public_domain"


class TestHathiTrustRights:
    @pytest.mark.parametrize("rights", ["pd", "pdus", "full view", "PD", "Full View"])
    def test_pd_rights(self, rights):
        assert compute_copyright_status({"hathitrust_rights": rights}) == "public_domain"

    @pytest.mark.parametrize("rights", ["ic", "ic-world", "limited (search-only)"])
    def test_ic_rights(self, rights):
        assert compute_copyright_status({"hathitrust_rights": rights}) == "in_copyright"

    def test_explicit_ic_wins_over_old_year(self):
        # Explicit HathiTrust in-copyright beats the pre-1930 year heuristic.
        book = {"hathitrust_rights": "ic", "first_published": 1850}
        assert compute_copyright_status(book) == "in_copyright"

    def test_pd_rights_independent_of_year(self):
        book = {"hathitrust_rights": "pd", "first_published": 1999}
        assert compute_copyright_status(book) == "public_domain"


class TestYearHeuristics:
    @pytest.mark.parametrize("year", [1500, 1900, 1930])
    def test_at_or_before_1930_is_public_domain(self, year):
        assert compute_copyright_status({"first_published": year}) == "public_domain"

    @pytest.mark.parametrize("year", [1931, 1950, 1963])
    def test_1931_to_1963_is_likely_pd(self, year):
        assert compute_copyright_status({"first_published": year}) == "likely_public_domain"

    @pytest.mark.parametrize("year", [1964, 2000, 2024])
    def test_after_1963_is_in_copyright(self, year):
        assert compute_copyright_status({"first_published": year}) == "in_copyright"


class TestUndetermined:
    def test_no_signal_is_undetermined(self):
        assert compute_copyright_status({}) == "undetermined"

    def test_blank_rights_no_year_is_undetermined(self):
        assert compute_copyright_status({"hathitrust_rights": ""}) == "undetermined"

    def test_unknown_rights_no_year_is_undetermined(self):
        # An unrecognized rights code falls through to the year heuristic.
        assert compute_copyright_status({"hathitrust_rights": "cc-by"}) == "undetermined"


def test_always_returns_valid_enum():
    for book in [{}, {"first_published": 1800}, {"first_published": 2020},
                 {"gutenberg_url": "x"}, {"hathitrust_rights": "ic"}]:
        assert compute_copyright_status(book) in VALID
