"""Tests for the additive-merge invariants — see issue #90."""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from json_merge import additive_merge, is_empty, load_existing, save_json


class TestIsEmpty:
    def test_none(self):
        assert is_empty(None)

    def test_empty_string(self):
        assert is_empty("")

    def test_empty_list(self):
        assert is_empty([])

    def test_empty_dict(self):
        assert is_empty({})

    def test_zero_is_not_empty(self):
        # birth_year=0 is unusual but not "missing"
        assert not is_empty(0)

    def test_false_is_not_empty(self):
        assert not is_empty(False)

    def test_string_value(self):
        assert not is_empty("a")


class TestAdditiveMerge:
    def test_fills_missing_fields(self):
        existing = {"name": "Plato"}
        new = {"name": "Plato", "bio": "philosopher", "birth_year": -428}
        changed = additive_merge(existing, new)
        assert changed
        assert existing["bio"] == "philosopher"
        assert existing["birth_year"] == -428

    def test_preserves_non_empty_existing_fields(self):
        """The core P0 invariant: never overwrite an existing non-empty value."""
        existing = {"bio": "old bio from last week", "photo_url": "https://example.com/photo.jpg"}
        new = {"bio": "shorter new bio", "photo_url": "https://example.com/different.jpg"}
        changed = additive_merge(existing, new)
        assert not changed
        assert existing["bio"] == "old bio from last week"
        assert existing["photo_url"] == "https://example.com/photo.jpg"

    def test_dead_api_does_not_wipe_data(self):
        """Issue #90 scenario: re-running enrichment when upstream returns nothing
        for fields that were previously populated must not nuke them."""
        existing = {
            "name": "A.A. Milne",
            "slug": "a-a-milne",
            "bio": "creator of Winnie-the-Pooh",
            "photo_url": "https://upload.wikimedia.org/wikipedia/commons/something.jpg",
        }
        # Simulate a re-run where Wikipedia REST returned no thumbnail and a redirect to
        # a stub page (no bio).
        new = {"name": "A.A. Milne", "slug": "a-a-milne", "book_count": 2}
        changed = additive_merge(existing, new)
        # No fields filled (book_count is set by caller separately, not via merge)
        assert "bio" in existing and existing["bio"] == "creator of Winnie-the-Pooh"
        assert "photo_url" in existing and existing["photo_url"].endswith("something.jpg")

    def test_empty_value_in_new_is_ignored(self):
        existing = {"bio": "an existing bio"}
        new = {"bio": "", "photo_url": None, "subjects": []}
        changed = additive_merge(existing, new)
        assert not changed
        assert existing["bio"] == "an existing bio"
        # Empty values in `new` shouldn't even create the key
        assert "photo_url" not in existing
        assert "subjects" not in existing

    def test_empty_existing_field_gets_filled(self):
        existing = {"name": "Plato", "bio": ""}
        new = {"bio": "the philosopher"}
        changed = additive_merge(existing, new)
        assert changed
        assert existing["bio"] == "the philosopher"

    def test_returns_false_when_nothing_changes(self):
        existing = {"name": "Plato", "bio": "philosopher"}
        new = {"name": "Plato", "bio": "philosopher"}
        assert not additive_merge(existing, new)

    def test_partial_fill(self):
        existing = {"bio": "kept", "photo_url": ""}
        new = {"bio": "ignored", "photo_url": "https://new.url/x.jpg", "wikipedia_url": "https://en.wikipedia.org/x"}
        changed = additive_merge(existing, new)
        assert changed
        assert existing["bio"] == "kept"
        assert existing["photo_url"] == "https://new.url/x.jpg"
        assert existing["wikipedia_url"] == "https://en.wikipedia.org/x"


class TestRoundtrip:
    def test_save_and_load(self, tmp_path: Path):
        f = tmp_path / "author.json"
        original = {"name": "Plato", "bio": "ancient", "subjects": ["philosophy"]}
        save_json(f, original)
        roundtripped = load_existing(f)
        assert roundtripped == original

    def test_load_missing_returns_empty(self, tmp_path: Path):
        assert load_existing(tmp_path / "missing.json") == {}

    def test_save_uses_2_space_indent_and_trailing_newline(self, tmp_path: Path):
        f = tmp_path / "x.json"
        save_json(f, {"a": 1})
        text = f.read_text()
        assert text.endswith("\n")
        assert '  "a": 1' in text

    def test_unicode_preserved(self, tmp_path: Path):
        """Author names like Albert‑László Barabási have non-ASCII chars."""
        f = tmp_path / "x.json"
        save_json(f, {"name": "Albert‑László Barabási"})
        roundtripped = load_existing(f)
        assert roundtripped["name"] == "Albert‑László Barabási"
        # Make sure ensure_ascii=False is in effect
        assert "Albert" in f.read_text()
