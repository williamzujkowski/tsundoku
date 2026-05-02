"""Tests for the Wikidata helpers — pure functions only, no network.

The module's network-fronting functions (qids_by_ol_work_keys, fetch_entity,
resolve_qid_labels) are integration-tested manually via smoke checks; here
we cover the pure response-parsing logic with synthetic Wikidata payloads
that mirror the real-world entity shape.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from wikidata import parse_wikidata_year, fields_for_book, fields_for_author, _value_id


def _entity(qid: str, claims: dict) -> dict:
    """Minimal Wikidata entity shape for testing."""
    return {"entities": {qid: {"claims": claims}}}


def _time_claim(time_str: str, precision: int = 9) -> dict:
    return {
        "mainsnak": {
            "datavalue": {
                "value": {"time": time_str, "precision": precision},
                "type": "time",
            }
        }
    }


def _wb_item_claim(qid: str, qualifiers: dict | None = None) -> dict:
    s = {
        "mainsnak": {
            "datavalue": {
                "value": {"id": qid, "entity-type": "item"},
                "type": "wikibase-entityid",
            }
        }
    }
    if qualifiers:
        s["qualifiers"] = qualifiers
    return s


def _monolingual_claim(text: str, language: str) -> dict:
    return {
        "mainsnak": {
            "datavalue": {
                "value": {"text": text, "language": language},
                "type": "monolingualtext",
            }
        }
    }


class TestParseWikidataYear:
    def test_precise_year(self):
        assert parse_wikidata_year({"time": "+1949-06-08T00:00:00Z", "precision": 11}) == (1949, False)

    def test_year_only_precision(self):
        assert parse_wikidata_year({"time": "+1949-00-00T00:00:00Z", "precision": 9}) == (1949, False)

    def test_century_precision_is_circa(self):
        # Precision 7 = century → circa
        assert parse_wikidata_year({"time": "+1900-00-00T00:00:00Z", "precision": 7}) == (1900, True)

    def test_bce(self):
        # Wikidata times can be negative for BCE
        assert parse_wikidata_year({"time": "-0428-00-00T00:00:00Z", "precision": 9}) == (-428, False)

    def test_none(self):
        assert parse_wikidata_year(None) == (None, False)

    def test_empty(self):
        assert parse_wikidata_year({"time": ""}) == (None, False)


class TestFieldsForBook:
    def test_minimal_entity_returns_qid_only(self):
        e = _entity("Q1", {})
        out = fields_for_book("Q1", e)
        assert out == {"wikidata_qid": "Q1"}

    def test_publication_date(self):
        e = _entity("Q208460", {
            "P577": [_time_claim("+1949-06-08T00:00:00Z", precision=11)],
        })
        out = fields_for_book("Q208460", e)
        assert out["first_published"] == 1949
        assert out["first_published_circa"] is False

    def test_picks_earliest_publication_date(self):
        e = _entity("Q1", {
            "P577": [
                _time_claim("+1949-06-08T00:00:00Z"),
                _time_claim("+1948-12-01T00:00:00Z"),  # earlier
                _time_claim("+1955-01-01T00:00:00Z"),
            ],
        })
        out = fields_for_book("Q1", e)
        assert out["first_published"] == 1948

    def test_language_eng(self):
        e = _entity("Q1", {"P407": [_wb_item_claim("Q1860")]})
        out = fields_for_book("Q1", e)
        assert out["original_language"] == "eng"

    def test_language_japanese(self):
        e = _entity("Q1", {"P407": [_wb_item_claim("Q5287")]})
        out = fields_for_book("Q1", e)
        assert out["original_language"] == "jpn"

    def test_language_unknown_qid_skipped(self):
        e = _entity("Q1", {"P407": [_wb_item_claim("Q9999999")]})
        out = fields_for_book("Q1", e)
        assert "original_language" not in out

    def test_title_english_preferred(self):
        e = _entity("Q1", {
            "P1476": [
                _monolingual_claim("海辺のカフカ", "ja"),
                _monolingual_claim("Kafka on the Shore", "en"),
            ],
        })
        out = fields_for_book("Q1", e)
        assert out["original_title"] == "Kafka on the Shore"

    def test_title_falls_back_to_first(self):
        e = _entity("Q1", {
            "P1476": [_monolingual_claim("Преступление и наказание", "ru")],
        })
        out = fields_for_book("Q1", e)
        assert out["original_title"] == "Преступление и наказание"

    def test_publisher_qid_recorded(self):
        # Underscore prefix = unresolved, needs label lookup
        e = _entity("Q1", {"P123": [_wb_item_claim("Q12345")]})
        out = fields_for_book("Q1", e)
        assert out["_publisher_qid"] == "Q12345"

    def test_award_with_year(self):
        award_q = {
            "P585": [{
                "datavalue": {
                    "value": {"time": "+1984-00-00T00:00:00Z", "precision": 9},
                    "type": "time",
                }
            }]
        }
        e = _entity("Q1", {"P166": [_wb_item_claim("Q123", qualifiers=award_q)]})
        out = fields_for_book("Q1", e)
        assert out["_awards"] == [{"_qid": "Q123", "year": 1984}]

    def test_series_with_position(self):
        position_q = {
            "P1545": [{"datavalue": {"value": "3", "type": "string"}}]
        }
        e = _entity("Q1", {"P179": [_wb_item_claim("QSeries", qualifiers=position_q)]})
        out = fields_for_book("Q1", e)
        assert out["_series"] == {"_qid": "QSeries", "position": 3}

    def test_circa_for_century_precision(self):
        e = _entity("Q1", {
            "P577": [_time_claim("+1900-00-00T00:00:00Z", precision=7)],
        })
        out = fields_for_book("Q1", e)
        assert out["first_published"] == 1900
        assert out["first_published_circa"] is True


class TestFieldsForAuthor:
    def test_minimal_returns_qid(self):
        e = _entity("Q1", {})
        assert fields_for_author("Q1", e) == {"wikidata_qid": "Q1"}

    def test_nationality_uk(self):
        e = _entity("Q3335", {"P27": [_wb_item_claim("Q145")]})
        out = fields_for_author("Q3335", e)
        assert out["nationality"] == ["GB"]

    def test_nationality_dual(self):
        e = _entity("Q1", {
            "P27": [_wb_item_claim("Q145"), _wb_item_claim("Q142")],  # GB + FR
        })
        out = fields_for_author("Q1", e)
        assert set(out["nationality"]) == {"GB", "FR"}

    def test_nationality_unknown_country_skipped(self):
        e = _entity("Q1", {"P27": [_wb_item_claim("Q9999999")]})
        out = fields_for_author("Q1", e)
        assert "nationality" not in out

    def test_pseudonyms(self):
        # P742 is a string-typed property
        e = _entity("Q1", {
            "P742": [
                {"mainsnak": {"datavalue": {"value": "George Orwell", "type": "string"}}},
                {"mainsnak": {"datavalue": {"value": "John Freeman", "type": "string"}}},
            ],
        })
        out = fields_for_author("Q1", e)
        assert out["alternate_names"] == ["George Orwell", "John Freeman"]

    def test_movements_recorded_as_qids(self):
        e = _entity("Q1", {
            "P135": [_wb_item_claim("Q12345"), _wb_item_claim("Q67890")],
        })
        out = fields_for_author("Q1", e)
        assert out["_movement_qids"] == ["Q12345", "Q67890"]

    def test_viaf(self):
        e = _entity("Q1", {
            "P214": [{"mainsnak": {"datavalue": {"value": "95155403", "type": "string"}}}],
        })
        out = fields_for_author("Q1", e)
        assert out["viaf_id"] == "95155403"

    def test_ol_author_key_cross_validation(self):
        e = _entity("Q1", {
            "P648": [{"mainsnak": {"datavalue": {"value": "OL118077A", "type": "string"}}}],
        })
        out = fields_for_author("Q1", e)
        assert out["ol_author_key"] == "/authors/OL118077A"

    def test_award_with_year_qualifier(self):
        award_q = {
            "P585": [{
                "datavalue": {
                    "value": {"time": "+1996-00-00T00:00:00Z", "precision": 9},
                    "type": "time",
                }
            }]
        }
        e = _entity("Q1", {"P166": [_wb_item_claim("Q549884", qualifiers=award_q)]})
        out = fields_for_author("Q1", e)
        assert out["_awards"] == [{"_qid": "Q549884", "year": 1996}]
