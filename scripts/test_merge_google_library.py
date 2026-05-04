"""Tests for merge-google-library title cleaning."""

import importlib.util
import os
import sys
from pathlib import Path

# merge-google-library.py uses a hyphen, so import it via spec
SCRIPT_PATH = Path(__file__).parent / "merge-google-library.py"
spec = importlib.util.spec_from_file_location("merge_google_library", SCRIPT_PATH)
mgl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mgl)


class TestCleanTitle:
    def test_smart_quotes(self):
        assert mgl.clean_title("It’s") == "It's"

    def test_em_dash(self):
        assert mgl.clean_title("Title — Subtitle") == "Title — Subtitle"

    def test_strips_quotes_and_whitespace(self):
        assert mgl.clean_title('  "Hamlet"  ') == "Hamlet"

    def test_filename_pattern_simple(self):
        # The original bug: "Cory_Doctorow_-_Homeland" → "Homeland"
        assert mgl.clean_title("Cory_Doctorow_-_Homeland") == "Homeland"

    def test_filename_pattern_with_extension(self):
        assert mgl.clean_title("Cory_Doctorow_-_Homeland.epub") == "Homeland"

    def test_filename_pattern_three_word_author(self):
        assert (
            mgl.clean_title("Ursula_K_Le_Guin_-_The_Dispossessed")
            == "The Dispossessed"
        )

    def test_filename_pattern_multiword_title(self):
        assert (
            mgl.clean_title("Frank_Herbert_-_Children_of_Dune")
            == "Children of Dune"
        )

    def test_real_title_with_dash_unaffected(self):
        # Spaces around dash → real title, not filename pattern
        assert (
            mgl.clean_title("Bertrand Russell - In Praise of Idleness")
            == "Bertrand Russell - In Praise of Idleness"
        )

    def test_lowercase_underscore_not_stripped(self):
        # lowercase prefix doesn't match author-name regex → leave alone
        assert mgl.clean_title("hello_world") == "hello_world"

    def test_single_token_before_dash_not_stripped(self):
        # Pattern requires 2+ underscore-joined TitleCase tokens
        assert mgl.clean_title("Author_-_Title") == "Author_-_Title"
