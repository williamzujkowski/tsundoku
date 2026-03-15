"""Tests for the shared title/author matching utilities."""

import pytest
from matching import title_similarity, strip_article, author_last_name, titles_match


class TestTitleSimilarity:
    def test_identical_titles(self):
        assert title_similarity("War and Peace", "War and Peace") == 1.0

    def test_completely_different(self):
        assert title_similarity("War and Peace", "Harry Potter") == 0.0

    def test_partial_overlap(self):
        score = title_similarity("The Republic", "Republic")
        assert 0.4 < score < 1.0

    def test_empty_string(self):
        assert title_similarity("", "Something") == 0.0
        assert title_similarity("Something", "") == 0.0

    def test_both_empty(self):
        assert title_similarity("", "") == 0.0

    def test_case_insensitive(self):
        assert title_similarity("WAR AND PEACE", "war and peace") == 1.0

    def test_subtitle_variation(self):
        # Punctuation attaches to words, reducing overlap
        score = title_similarity(
            "Moby Dick",
            "Moby Dick; or, The Whale"
        )
        assert score > 0.1  # some overlap despite punctuation

    def test_single_word(self):
        assert title_similarity("Dracula", "Dracula") == 1.0


class TestStripArticle:
    def test_strip_a(self):
        assert strip_article("A Christmas Carol") == "Christmas Carol"

    def test_strip_an(self):
        assert strip_article("An Essay on Man") == "Essay on Man"

    def test_strip_the(self):
        assert strip_article("The Republic") == "Republic"

    def test_no_article(self):
        assert strip_article("War and Peace") == "War and Peace"

    def test_article_in_middle(self):
        assert strip_article("Murder on the Orient Express") == "Murder on the Orient Express"

    def test_empty_string(self):
        assert strip_article("") == ""

    def test_just_article(self):
        assert strip_article("A ") == ""


class TestAuthorLastName:
    def test_normal_name(self):
        assert author_last_name("Leo Tolstoy") == "tolstoy"

    def test_single_name(self):
        assert author_last_name("Plato") == "plato"

    def test_multiple_names(self):
        assert author_last_name("Gabriel Garcia Marquez") == "marquez"

    def test_empty_string(self):
        assert author_last_name("") == ""

    def test_whitespace(self):
        assert author_last_name("  Leo Tolstoy  ") == "tolstoy"


class TestTitlesMatch:
    def test_exact_match(self):
        assert titles_match("War and Peace", "War and Peace")

    def test_containment(self):
        assert titles_match("Republic", "The Republic")

    def test_reverse_containment(self):
        assert titles_match("The Republic", "Republic")

    def test_no_match(self):
        assert not titles_match("War and Peace", "Harry Potter")

    def test_high_overlap(self):
        assert titles_match(
            "A Connecticut Yankee in King Arthur's Court",
            "Connecticut Yankee in King Arthur's Court"
        )

    def test_low_overlap(self):
        assert not titles_match("The Great Gatsby", "The Great Wall of China")

    def test_case_insensitive(self):
        assert titles_match("DRACULA", "dracula")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
