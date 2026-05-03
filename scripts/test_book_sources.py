"""Tests for the multi-source book enricher (Wikidata P18 / Wikipedia REST /
Open Library editions / Google Books) and the cover_via_chain orchestrator.
Network is fully mocked."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import book_sources as src
from http_cache import reset_default_cache


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path):
    """Each test gets a fresh in-memory http_cache."""
    reset_default_cache(tmp_path / "cache.sqlite")
    yield


class TestWikidataBook:
    def test_extracts_p18_image(self, monkeypatch):
        monkeypatch.setattr(
            src,
            "_fetch_json",
            lambda url: {
                "entities": {
                    "Q1": {
                        "claims": {
                            "P18": [{"mainsnak": {"datavalue": {"value": "Cover.jpg"}}}],
                        }
                    }
                }
            },
        )
        out = src.from_wikidata_book(qid="Q1")
        assert "Special:FilePath/Cover.jpg" in out["cover_url"]

    def test_returns_empty_on_blank_qid(self):
        assert src.from_wikidata_book(qid="") == {}

    def test_returns_empty_on_no_p18(self, monkeypatch):
        monkeypatch.setattr(
            src,
            "_fetch_json",
            lambda url: {"entities": {"Q1": {"claims": {}}}},
        )
        assert src.from_wikidata_book(qid="Q1") == {}

    def test_skips_invalid_p18_entries(self, monkeypatch):
        """A claim that doesn't follow the expected shape shouldn't crash."""
        monkeypatch.setattr(
            src,
            "_fetch_json",
            lambda url: {
                "entities": {
                    "Q1": {
                        "claims": {
                            "P18": [
                                {"mainsnak": {}},  # broken
                                {"mainsnak": {"datavalue": {"value": "Good.jpg"}}},
                            ]
                        }
                    }
                }
            },
        )
        out = src.from_wikidata_book(qid="Q1")
        assert "Good.jpg" in out["cover_url"]


class TestWikipediaBook:
    def test_returns_originalimage(self, monkeypatch):
        monkeypatch.setattr(
            src,
            "_fetch_json",
            lambda url: {
                "type": "standard",
                "originalimage": {"source": "https://upload.wikimedia.org/foo.jpg"},
            },
        )
        out = src.from_wikipedia_book(title="Foo")
        assert out["cover_url"] == "https://upload.wikimedia.org/foo.jpg"

    def test_falls_back_to_thumbnail(self, monkeypatch):
        monkeypatch.setattr(
            src,
            "_fetch_json",
            lambda url: {
                "type": "standard",
                "thumbnail": {"source": "https://upload.wikimedia.org/thumb.jpg"},
            },
        )
        out = src.from_wikipedia_book(title="Foo")
        assert out["cover_url"] == "https://upload.wikimedia.org/thumb.jpg"

    def test_skips_disambiguation(self, monkeypatch):
        monkeypatch.setattr(
            src,
            "_fetch_json",
            lambda url: {"type": "disambiguation"},
        )
        assert src.from_wikipedia_book(title="The Stranger") == {}

    def test_rejects_non_wiki_image(self, monkeypatch):
        monkeypatch.setattr(
            src,
            "_fetch_json",
            lambda url: {
                "type": "standard",
                "originalimage": {"source": "https://example.com/foo.jpg"},
            },
        )
        assert src.from_wikipedia_book(title="Foo") == {}

    def test_returns_empty_on_404(self, monkeypatch):
        monkeypatch.setattr(src, "_fetch_json", lambda url: None)
        assert src.from_wikipedia_book(title="Foo") == {}

    def test_returns_empty_on_blank_title(self):
        assert src.from_wikipedia_book(title="") == {}


class TestOpenLibraryEditions:
    def test_returns_first_valid_cover(self, monkeypatch):
        monkeypatch.setattr(
            src,
            "_fetch_json",
            lambda url: {
                "entries": [
                    {"covers": []},  # no cover — skip
                    {"covers": [-1]},  # OL "no cover" sentinel — skip
                    {"covers": [12345]},  # match
                    {"covers": [99999]},  # later — should not be picked
                ]
            },
        )
        out = src.from_open_library_editions(work_key="OL1W")
        assert out["cover_url"].endswith("12345-M.jpg")
        assert out["cover_url_large"].endswith("12345-L.jpg")

    def test_returns_empty_on_no_editions(self, monkeypatch):
        monkeypatch.setattr(src, "_fetch_json", lambda url: {"entries": []})
        assert src.from_open_library_editions(work_key="OL1W") == {}

    def test_returns_empty_on_blank_key(self):
        assert src.from_open_library_editions(work_key="") == {}

    def test_handles_work_key_without_prefix(self, monkeypatch):
        captured = {}

        def fetch(url):
            captured["url"] = url
            return None

        monkeypatch.setattr(src, "_fetch_json", fetch)
        src.from_open_library_editions(work_key="OL1W")
        assert "/works/OL1W/editions.json" in captured["url"]


class TestGoogleBooks:
    def test_isbn_lookup(self, monkeypatch):
        monkeypatch.setattr(
            src,
            "_fetch_json",
            lambda url: {
                "items": [
                    {
                        "volumeInfo": {
                            "imageLinks": {
                                "thumbnail": "http://books.google.com/foo.jpg",
                            }
                        }
                    }
                ]
            },
        )
        out = src.from_google_books(isbn="9780000000000")
        # http → https forced
        assert out["cover_url"].startswith("https://")

    def test_prefers_large_over_thumbnail(self, monkeypatch):
        monkeypatch.setattr(
            src,
            "_fetch_json",
            lambda url: {
                "items": [
                    {
                        "volumeInfo": {
                            "imageLinks": {
                                "smallThumbnail": "https://x/small.jpg",
                                "thumbnail": "https://x/thumb.jpg",
                                "large": "https://x/large.jpg",
                            }
                        }
                    }
                ]
            },
        )
        out = src.from_google_books(isbn="X")
        assert out["cover_url"] == "https://x/large.jpg"

    def test_title_author_fallback(self, monkeypatch):
        captured = {}

        def fetch(url):
            captured["url"] = url
            return {"items": []}

        monkeypatch.setattr(src, "_fetch_json", fetch)
        src.from_google_books(title="Foo", author="Bar")
        assert "intitle:Foo" in captured["url"]
        assert "inauthor:Bar" in captured["url"]

    def test_returns_empty_with_neither_isbn_nor_title(self):
        assert src.from_google_books() == {}

    def test_returns_empty_on_no_items(self, monkeypatch):
        monkeypatch.setattr(src, "_fetch_json", lambda url: {"items": []})
        assert src.from_google_books(isbn="X") == {}


class TestCoverViaChain:
    def test_wikidata_wins_when_qid_present(self, monkeypatch):
        monkeypatch.setattr(src, "from_wikidata_book", lambda qid: {"cover_url": "wd"})
        monkeypatch.setattr(src, "from_wikipedia_book", lambda title: {"cover_url": "wp"})
        out, source = src.cover_via_chain({"wikidata_qid": "Q1", "title": "Foo"})
        assert out["cover_url"] == "wd"
        assert source == "wikidata_book_v1"

    def test_falls_through_to_wikipedia(self, monkeypatch):
        monkeypatch.setattr(src, "from_wikidata_book", lambda qid: {})
        monkeypatch.setattr(src, "from_wikipedia_book", lambda title: {"cover_url": "wp"})
        out, source = src.cover_via_chain({"wikidata_qid": "Q1", "title": "Foo"})
        assert source == "wikipedia_book_v1"

    def test_falls_through_to_ol_editions(self, monkeypatch):
        monkeypatch.setattr(src, "from_wikidata_book", lambda qid: {})
        monkeypatch.setattr(src, "from_wikipedia_book", lambda title: {})
        monkeypatch.setattr(src, "from_open_library_editions",
                            lambda work_key: {"cover_url": "ol"})
        out, source = src.cover_via_chain({"title": "Foo", "ol_work_key": "OL1W"})
        assert source == "ol_editions_v1"

    def test_falls_through_to_google_books(self, monkeypatch):
        monkeypatch.setattr(src, "from_wikidata_book", lambda qid: {})
        monkeypatch.setattr(src, "from_wikipedia_book", lambda title: {})
        monkeypatch.setattr(src, "from_open_library_editions", lambda work_key: {})
        monkeypatch.setattr(src, "from_google_books",
                            lambda isbn=None, title=None, author=None: {"cover_url": "gb"})
        out, source = src.cover_via_chain({"title": "Foo", "isbn": "X", "author": "A"})
        assert source == "google_books_v1"

    def test_returns_none_on_total_miss(self, monkeypatch):
        monkeypatch.setattr(src, "from_wikidata_book", lambda qid: {})
        monkeypatch.setattr(src, "from_wikipedia_book", lambda title: {})
        monkeypatch.setattr(src, "from_open_library_editions", lambda work_key: {})
        monkeypatch.setattr(src, "from_google_books",
                            lambda isbn=None, title=None, author=None: {})
        out, source = src.cover_via_chain({"title": "Foo"})
        assert out == {}
        assert source is None
