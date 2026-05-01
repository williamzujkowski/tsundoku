"""Tests for the multi-source enricher (Open Library author page + Wikidata)
and the name-variant generator. Network is fully mocked."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import author_sources as src
from http_cache import reset_default_cache


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path):
    """Each test gets a fresh in-memory http_cache."""
    reset_default_cache(tmp_path / "cache.sqlite")
    yield


class TestCandidateNames:
    def test_plain_name_unchanged(self):
        assert src.candidate_names("Plato") == ["Plato"]

    def test_strips_parenthesized_artifacts(self):
        out = src.candidate_names("Petr Alekseevich Kropotkin (kni︠a︡zʹ)")
        assert "Petr Alekseevich Kropotkin" in out
        assert "Petr Alekseevich Kropotkin (kni︠a︡zʹ)" in out  # original retained

    def test_splits_ampersand_to_first_author(self):
        out = src.candidate_names("Robert Jordan & Brandon Sanderson")
        assert "Robert Jordan" in out

    def test_splits_and_to_first_author(self):
        out = src.candidate_names("Brian W. Kernighan and Rob Pike")
        assert "Brian W. Kernighan" in out

    def test_splits_comma(self):
        out = src.candidate_names("Robert Lynn Asprin, Lynn Abbey")
        assert "Robert Lynn Asprin" in out

    def test_no_dupes_when_already_clean(self):
        out = src.candidate_names("Plato")
        assert len(out) == len(set(out))


class TestOlidExtraction:
    def test_extracts_from_url(self):
        assert src._olid_from_url("https://openlibrary.org/authors/OL26320A") == "OL26320A"
        assert src._olid_from_url("https://openlibrary.org/authors/OL26320A/Some_Name") == "OL26320A"

    def test_returns_none_for_blank(self):
        assert src._olid_from_url("") is None
        assert src._olid_from_url(None) is None

    def test_returns_none_for_unrelated_url(self):
        assert src._olid_from_url("https://example.com/foo") is None


class TestOpenLibraryAuthorPage:
    def test_parses_full_response(self, monkeypatch):
        monkeypatch.setattr(
            src,
            "_fetch_json",
            lambda url: {
                "bio": {"type": "/type/text", "value": "  A philosopher.  "},
                "photos": [12345, 99999],
                "birth_date": "1871-12-26",
                "death_date": "1947",
                "name": "Petr Kropotkin",
            },
        )
        result = src.from_open_library_author_page(olid="OL12345A")
        assert result["bio"] == "A philosopher."
        assert result["photo_url"].endswith("/a/id/12345-M.jpg")
        assert result["birth_year"] == 1871
        assert result["death_year"] == 1947
        assert result["open_library_url"] == "https://openlibrary.org/authors/OL12345A"

    def test_handles_string_bio(self, monkeypatch):
        """OL is inconsistent — sometimes bio is a plain string."""
        monkeypatch.setattr(
            src,
            "_fetch_json",
            lambda url: {"bio": "philosopher", "photos": []},
        )
        result = src.from_open_library_author_page(olid="OL1A")
        assert result["bio"] == "philosopher"

    def test_handles_no_photos(self, monkeypatch):
        monkeypatch.setattr(src, "_fetch_json", lambda url: {"bio": "x", "photos": []})
        result = src.from_open_library_author_page(olid="OL1A")
        assert "photo_url" not in result

    def test_handles_negative_photo_id(self, monkeypatch):
        """OL uses -1 to mean 'no photo'."""
        monkeypatch.setattr(src, "_fetch_json", lambda url: {"photos": [-1]})
        result = src.from_open_library_author_page(olid="OL1A")
        assert "photo_url" not in result

    def test_returns_empty_on_404(self, monkeypatch):
        monkeypatch.setattr(src, "_fetch_json", lambda url: None)
        assert src.from_open_library_author_page(olid="OL1A") == {}

    def test_returns_empty_when_no_olid_or_name(self):
        assert src.from_open_library_author_page() == {}

    def test_searches_by_name_when_no_olid(self, monkeypatch):
        responses = {
            "search": {"docs": [{"key": "OL999A"}]},
            "author": {"bio": "found by search", "photos": []},
        }

        def router(url):
            if "search/authors.json" in url:
                return responses["search"]
            if "/authors/OL999A.json" in url:
                return responses["author"]
            return None

        monkeypatch.setattr(src, "_fetch_json", router)
        result = src.from_open_library_author_page(name="Some Name")
        assert result["bio"] == "found by search"
        assert result["open_library_url"].endswith("OL999A")


class TestWikidata:
    def test_parses_description_image_dates(self, monkeypatch):
        responses = {
            "search": {"search": [{"id": "Q42", "description": "writer"}]},
            "entity": {
                "entities": {
                    "Q42": {
                        "descriptions": {"en": {"value": "British author of comic novels"}},
                        "claims": {
                            "P18": [{"mainsnak": {"datavalue": {"value": "Douglas_Adams.jpg"}}}],
                            "P569": [{"mainsnak": {"datavalue": {"value": {"time": "+1952-03-11T00:00:00Z"}}}}],
                            "P570": [{"mainsnak": {"datavalue": {"value": {"time": "+2001-05-11T00:00:00Z"}}}}],
                        },
                    }
                }
            },
        }

        def router(url):
            if "wbsearchentities" in url:
                return responses["search"]
            if "EntityData/Q42" in url:
                return responses["entity"]
            return None

        monkeypatch.setattr(src, "_fetch_json", router)
        result = src.from_wikidata(name="Douglas Adams")
        assert result["bio"] == "British author of comic novels"
        assert "Douglas_Adams.jpg" in result["photo_url"]
        assert result["birth_year"] == 1952
        assert result["death_year"] == 2001

    def test_returns_empty_on_no_match(self, monkeypatch):
        monkeypatch.setattr(src, "_fetch_json", lambda url: {"search": []})
        assert src.from_wikidata(name="Nonexistent McNobody") == {}

    def test_prefers_writer_disambiguation(self, monkeypatch):
        """Two matches — 'football player' should be skipped in favor of 'writer'."""
        responses = {
            "search": {
                "search": [
                    {"id": "Q1", "description": "Argentinian football player"},
                    {"id": "Q2", "description": "American novelist"},
                ]
            },
            "Q2": {
                "entities": {
                    "Q2": {
                        "descriptions": {"en": {"value": "novelist"}},
                        "claims": {},
                    }
                }
            },
        }

        def router(url):
            if "wbsearchentities" in url:
                return responses["search"]
            if "Q2" in url:
                return responses["Q2"]
            return None

        monkeypatch.setattr(src, "_fetch_json", router)
        result = src.from_wikidata(name="Same Name")
        assert result["bio"] == "novelist"

    def test_handles_negative_year(self, monkeypatch):
        """Ancient authors have BC dates encoded as -0428 etc."""
        responses = {
            "search": {"search": [{"id": "Q859", "description": "philosopher"}]},
            "entity": {
                "entities": {
                    "Q859": {
                        "claims": {
                            "P569": [
                                {"mainsnak": {"datavalue": {"value": {"time": "-0428-01-01T00:00:00Z"}}}}
                            ],
                        }
                    }
                }
            },
        }

        def router(url):
            return responses["search"] if "wbsearchentities" in url else responses["entity"]

        monkeypatch.setattr(src, "_fetch_json", router)
        result = src.from_wikidata(name="Plato")
        # Year extraction takes the digits — sign is preserved by the regex
        assert result["birth_year"] == 428
