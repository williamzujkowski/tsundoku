"""Tests for the improved dedupe normalization (#113 follow-up)."""

import importlib.util
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

# Module name has a hyphen, so import via spec.
_spec = importlib.util.spec_from_file_location(
    "dedupe_books", Path(__file__).parent / "dedupe-books.py"
)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


class TestNormalizeTitle:
    def test_strips_leading_article(self):
        assert mod.normalize_title("The Cyberiad") == mod.normalize_title("Cyberiad")

    def test_strips_comma(self):
        # Real-world dupe: "Thinking Fast and Slow" vs "Thinking, Fast and Slow"
        assert mod.normalize_title("Thinking Fast and Slow") == mod.normalize_title(
            "Thinking, Fast and Slow"
        )

    def test_strips_apostrophe(self):
        # Real-world dupe: "Gravitys Rainbow" vs "Gravity's Rainbow"
        assert mod.normalize_title("Gravitys Rainbow") == mod.normalize_title(
            "Gravity's Rainbow"
        )

    def test_strips_colon(self):
        # "Compilers Principles Techniques and Tools" vs "Compilers: Principles, Techniques, and Tools"
        assert mod.normalize_title(
            "Compilers Principles Techniques and Tools"
        ) == mod.normalize_title("Compilers: Principles, Techniques, and Tools")

    def test_strips_hyphen(self):
        assert mod.normalize_title(
            "Tractatus Logico-Philosophicus"
        ) == mod.normalize_title("Tractatus Logico Philosophicus")

    def test_strips_question_mark(self):
        assert mod.normalize_title("What Is Mathematics?") == mod.normalize_title(
            "What Is Mathematics"
        )

    def test_collapses_multiple_spaces(self):
        assert mod.normalize_title("a  b   c") == mod.normalize_title("a b c")

    def test_strips_parens(self):
        assert mod.normalize_title("Foo (1st Edition)") == mod.normalize_title("Foo")

    def test_distinguishes_genuinely_different_titles(self):
        # Sanity: dedup logic shouldn't collapse different books
        assert mod.normalize_title("1984") != mod.normalize_title("1Q84")
        assert mod.normalize_title("Solaris") != mod.normalize_title("Solaria")


class TestNormalizeAuthor:
    def test_single_author_unchanged(self):
        assert mod.normalize_author("Plato") == "plato"

    def test_strips_punctuation_in_single_name(self):
        # "A.A. Milne" → "a a milne" — periods become spaces, then collapse
        result = mod.normalize_author("A.A. Milne")
        assert "milne" in result

    def test_collapses_two_author_format_variants(self):
        """The cross-author-format case from #113."""
        # Both reduce to "acemoglu|robinson" by last names
        a = mod.normalize_author("Acemoglu & Robinson")
        b = mod.normalize_author("Daron Acemoglu and James A. Robinson")
        assert a == b == "acemoglu|robinson"

    def test_collapses_three_author(self):
        # "Aho, Lam, Sethi, and Ullman" should match a 4-author full-names version
        a = mod.normalize_author("Aho, Lam, Sethi, and Ullman")
        b = mod.normalize_author("Alfred V. Aho and Monica S. Lam and Ravi Sethi and Jeffrey D. Ullman")
        assert a == b == "aho|lam|sethi|ullman"

    def test_does_not_match_unrelated_authors(self):
        assert mod.normalize_author("Plato") != mod.normalize_author("Aristotle")

    def test_handles_ampersand_with_titles(self):
        # "Courant & Robbins" vs "Richard Courant and Herbert Robbins"
        a = mod.normalize_author("Courant & Robbins")
        b = mod.normalize_author("Richard Courant and Herbert Robbins")
        assert a == b == "courant|robbins"

    def test_lowercase(self):
        assert mod.normalize_author("PLATO") == mod.normalize_author("plato")

    def test_handles_anselm_variants(self):
        """Real-world: "Anselm" vs "Anselm of Canterbury"."""
        # These DON'T match (single-name treated as one token; "Anselm of Canterbury"
        # has multiple). Documenting current behavior — possibly worth a future
        # heuristic but punctuation-stripping shouldn't make false positives.
        assert mod.normalize_author("Anselm") != mod.normalize_author("Anselm of Canterbury")


class TestEnrichmentScore:
    def test_counts_populated_fields(self):
        book = {"description": "a book", "cover_url": "https://x.jpg", "isbn": ""}
        # description and cover_url count, isbn is empty
        assert mod.enrichment_score(book) == 2

    def test_empty_book(self):
        assert mod.enrichment_score({}) == 0


class TestMergeBooks:
    def test_fills_missing_in_keep(self):
        keep = {"slug": "k", "title": "K", "description": ""}
        remove = {"slug": "r", "title": "R", "description": "merged in", "isbn": "123"}
        result = mod.merge_books(keep, remove)
        assert result["description"] == "merged in"
        assert result["isbn"] == "123"

    def test_does_not_overwrite_existing(self):
        keep = {"slug": "k", "title": "K", "description": "kept"}
        remove = {"slug": "r", "description": "ignored"}
        result = mod.merge_books(keep, remove)
        assert result["description"] == "kept"

    def test_does_not_overwrite_identity_fields(self):
        keep = {"slug": "k", "title": "Keep Title"}
        remove = {"slug": "r", "title": "Other Title"}
        result = mod.merge_books(keep, remove)
        assert result["slug"] == "k"
        assert result["title"] == "Keep Title"

    def test_merges_arrays(self):
        keep = {"slug": "k", "tags": ["a", "b"]}
        remove = {"slug": "r", "tags": ["b", "c"]}
        result = mod.merge_books(keep, remove)
        assert result["tags"] == ["a", "b", "c"]
