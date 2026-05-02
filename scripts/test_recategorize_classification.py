"""Tests for the DDC/LCC classification → category mapping in recategorize.py."""

import importlib.util
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

_spec = importlib.util.spec_from_file_location(
    "recategorize", Path(__file__).parent / "recategorize.py"
)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


CATS = {
    "Literature", "Poetry", "Drama", "Literary Criticism",
    "Philosophy", "Religion", "Political Theory", "Economics",
    "Mathematics", "Science", "Computer Science", "History", "Classics",
}


class TestDDCMapping:
    def test_823_is_literature(self):
        # English fiction
        assert mod.category_from_ddc(["823.6"]) == "Literature"

    def test_813_is_literature(self):
        # American fiction
        assert mod.category_from_ddc(["813.54"]) == "Literature"

    def test_811_is_poetry(self):
        # American poetry (last digit 1)
        assert mod.category_from_ddc(["811.52"]) == "Poetry"

    def test_822_is_drama(self):
        # English drama (last digit 2)
        assert mod.category_from_ddc(["822.33"]) == "Drama"

    def test_809_is_literary_criticism(self):
        assert mod.category_from_ddc(["809"]) == "Literary Criticism"

    def test_191_is_philosophy(self):
        assert mod.category_from_ddc(["191"]) == "Philosophy"

    def test_230_is_religion(self):
        assert mod.category_from_ddc(["230"]) == "Religion"

    def test_320_is_political_theory(self):
        assert mod.category_from_ddc(["320.1"]) == "Political Theory"

    def test_330_is_economics(self):
        assert mod.category_from_ddc(["330.94"]) == "Economics"

    def test_510_is_mathematics(self):
        assert mod.category_from_ddc(["510"]) == "Mathematics"

    def test_530_is_science(self):
        # Physics
        assert mod.category_from_ddc(["530.12"]) == "Science"

    def test_909_is_history(self):
        # Sapiens — DDC 909 (world history)
        assert mod.category_from_ddc(["909"]) == "History"

    def test_005_is_computer_science(self):
        # Computer programming
        assert mod.category_from_ddc(["005.13"]) == "Computer Science"

    def test_takes_first_parseable_entry(self):
        # OL often returns multiple — we use the first numeric one
        assert mod.category_from_ddc(["[Fic]", "823.6"]) == "Literature"

    def test_returns_none_on_unparseable(self):
        assert mod.category_from_ddc([]) is None
        assert mod.category_from_ddc(["[Fic]"]) is None


class TestLCCMapping:
    def test_PR_is_literature(self):
        # English literature (Austen, Orwell)
        assert mod.category_from_lcc(["PR-4034.00000000.P7"]) == "Literature"

    def test_PS_is_literature(self):
        # American literature (McCarthy)
        assert mod.category_from_lcc(["PS-3563.00000000.C337"]) == "Literature"

    def test_PA_is_classics(self):
        # Greek/Latin
        assert mod.category_from_lcc(["PA-3613"]) == "Classics"

    def test_PN_is_literary_criticism(self):
        assert mod.category_from_lcc(["PN-1010"]) == "Literary Criticism"

    def test_D_is_history(self):
        assert mod.category_from_lcc(["D-731"]) == "History"

    def test_E_is_history(self):
        assert mod.category_from_lcc(["E-184"]) == "History"

    def test_QA_is_mathematics(self):
        assert mod.category_from_lcc(["QA-303"]) == "Mathematics"

    def test_QA76_is_computer_science(self):
        assert mod.category_from_lcc(["QA76.73.P98"]) == "Computer Science"

    def test_BL_is_religion(self):
        assert mod.category_from_lcc(["BL-1825"]) == "Religion"

    def test_B_is_philosophy(self):
        # Plain B = philosophy (not religion subclass)
        assert mod.category_from_lcc(["B-3318"]) == "Philosophy"

    def test_J_is_political_theory(self):
        assert mod.category_from_lcc(["JC-571"]) == "Political Theory"

    def test_HB_is_economics(self):
        assert mod.category_from_lcc(["HB-3711"]) == "Economics"

    def test_returns_none_on_unrecognized(self):
        assert mod.category_from_lcc([]) is None
        assert mod.category_from_lcc(["XX-9999"]) is None


class TestCombined:
    def test_ddc_and_lcc_agree(self):
        book = {"ddc": ["823.6"], "lcc": ["PR-4034"], "category": "Mystery"}
        assert mod.category_from_classification(book, CATS) == "Literature"

    def test_ddc_and_lcc_disagree_returns_none(self):
        # Conservative — if classifications disagree, we don't guess.
        book = {"ddc": ["823.6"], "lcc": ["QA-76"], "category": "Other"}
        result = mod.category_from_classification(book, CATS)
        assert result is None

    def test_only_ddc_present(self):
        book = {"ddc": ["813.54"], "category": "Mystery"}
        assert mod.category_from_classification(book, CATS) == "Literature"

    def test_only_lcc_present(self):
        book = {"lcc": ["PS-3563"], "category": "Mystery"}
        assert mod.category_from_classification(book, CATS) == "Literature"

    def test_no_change_when_already_correct(self):
        book = {"ddc": ["823.6"], "lcc": ["PR-4034"], "category": "Literature"}
        assert mod.category_from_classification(book, CATS) is None

    def test_target_must_exist_in_catalog(self):
        # If "Literature" weren't a category, we wouldn't suggest it.
        book = {"ddc": ["823.6"], "category": "X"}
        assert mod.category_from_classification(book, set()) is None

    def test_real_world_1984_to_literature(self):
        # OL returns ddc=['823'] and lcc=['PR-6029...'] for 1984
        book = {
            "ddc": ["813", "823.912"],
            "lcc": ["PR-6029.00000000.R8 N5 1949"],
            "category": "Mystery",
        }
        assert mod.category_from_classification(book, CATS) == "Literature"

    def test_real_world_sapiens_to_history(self):
        # OL: ddc=['909'], lcc=['CB-...']
        book = {"ddc": ["909"], "lcc": ["CB-0025"], "category": "History"}
        # Sapiens is already in History — no move needed
        assert mod.category_from_classification(book, CATS) is None
