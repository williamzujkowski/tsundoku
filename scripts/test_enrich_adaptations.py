"""Tests for Wikidata P144 adaptations parsing (issue #184).

Mocks the SPARQL layer (wikidata._sparql) — no network. Asserts that a
synthetic SPARQL results payload parses into correct {type, title, year}
objects: every type mapping, missing-year, dedup, multi-P31 priority,
the per-book cap, and label==QID skipping.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import wikidata
from wikidata import (
    adaptations_for_books,
    adaptations_for_batch,
    _classify_adaptation_types,
    _year_from_iso,
    MAX_ADAPTATIONS_PER_BOOK,
)


# --- SPARQL payload helpers ------------------------------------------------

def _row(book_qid, work_qid, label, *, date=None, inception=None, p31=None):
    """Build one SPARQL result row (one P31 per row) matching the real shape."""
    b = {
        "book": {"value": f"http://www.wikidata.org/entity/{book_qid}"},
        "work": {"value": f"http://www.wikidata.org/entity/{work_qid}"},
        "workLabel": {"value": label},
    }
    if date is not None:
        b["date"] = {"value": date}
    if inception is not None:
        b["inception"] = {"value": inception}
    if p31 is not None:
        b["p31"] = {"value": f"http://www.wikidata.org/entity/{p31}"}
    return b


def _binding(book_qid, work_qid, label, *, date=None, inception=None, p31s=()):
    """Expand one logical work (which may have several P31 classes) into the
    one-row-per-P31 shape the live query returns. Returns a list of rows."""
    if not p31s:
        return [_row(book_qid, work_qid, label, date=date, inception=inception)]
    return [
        _row(book_qid, work_qid, label, date=date, inception=inception, p31=q)
        for q in p31s
    ]


def _results(rows_or_groups):
    """Accept a flat list of rows and/or lists-of-rows (from _binding) and
    flatten into the SPARQL results shape."""
    flat = []
    for item in rows_or_groups:
        if isinstance(item, list):
            flat.extend(item)
        else:
            flat.append(item)
    return {"results": {"bindings": flat}}


def _patch_sparql(monkeypatch, payload):
    """Force adaptations_for_books to use `payload` for every batch and skip
    the disk cache (call the fetch closure directly)."""
    monkeypatch.setattr(wikidata, "_sparql", lambda q: payload)
    # Bypass the on-disk cache so the patched _sparql is actually exercised.
    monkeypatch.setattr(
        wikidata, "cached_fetch", lambda source, key, fetch, **kw: fetch()
    )


# --- _year_from_iso --------------------------------------------------------

class TestYearFromIso:
    def test_iso_datetime(self):
        assert _year_from_iso("1965-08-01T00:00:00Z") == 1965

    def test_year_only(self):
        assert _year_from_iso("1984") == 1984

    def test_bce_negative(self):
        assert _year_from_iso("-0428-00-00T00:00:00Z") == -428

    def test_none(self):
        assert _year_from_iso(None) is None

    def test_garbage(self):
        assert _year_from_iso("not-a-date") is None


# --- _classify_adaptation_types -------------------------------------------

class TestClassify:
    def test_film(self):
        assert _classify_adaptation_types(["Q11424"]) == "film"

    def test_tv_series(self):
        assert _classify_adaptation_types(["Q5398426"]) == "tv"

    def test_stage_play(self):
        assert _classify_adaptation_types(["Q25379"]) == "stage"

    def test_radio_drama(self):
        assert _classify_adaptation_types(["Q2635894"]) == "radio"

    def test_opera(self):
        assert _classify_adaptation_types(["Q1344"]) == "opera"

    def test_unknown_is_other(self):
        assert _classify_adaptation_types(["Q9999999"]) == "other"

    def test_empty_is_other(self):
        assert _classify_adaptation_types([]) == "other"

    def test_tv_wins_over_film_for_television_film(self):
        # A work tagged both 'film' (Q11424) and 'television film' (Q93204)
        # must resolve to tv per the fixed priority.
        assert _classify_adaptation_types(["Q11424", "Q93204"]) == "tv"

    def test_film_wins_over_stage_when_both_present(self):
        assert _classify_adaptation_types(["Q25379", "Q11424"]) == "film"


# --- adaptations_for_books (the parser) -----------------------------------

class TestAdaptationsForBooks:
    def test_each_type_mapping(self, monkeypatch):
        payload = _results([
            _binding("Q1", "QF", "A Film", date="1984-01-01T00:00:00Z", p31s=["Q11424"]),
            _binding("Q1", "QT", "A Series", date="2000-01-01T00:00:00Z", p31s=["Q5398426"]),
            _binding("Q1", "QS", "A Play", date="1990-01-01T00:00:00Z", p31s=["Q25379"]),
            _binding("Q1", "QR", "A Radio Drama", date="1955-01-01T00:00:00Z", p31s=["Q2635894"]),
            _binding("Q1", "QO", "An Opera", date="1875-01-01T00:00:00Z", p31s=["Q1344"]),
            _binding("Q1", "QX", "Something Else", date="2010-01-01T00:00:00Z", p31s=["Q9999999"]),
        ])
        _patch_sparql(monkeypatch, payload)
        out = adaptations_for_books(["Q1"])
        got = {(a["type"], a["title"], a.get("year")) for a in out["Q1"]}
        assert got == {
            ("opera", "An Opera", 1875),
            ("radio", "A Radio Drama", 1955),
            ("film", "A Film", 1984),
            ("stage", "A Play", 1990),
            ("tv", "A Series", 2000),
            ("other", "Something Else", 2010),
        }

    def test_sorted_by_year(self, monkeypatch):
        payload = _results([
            _binding("Q1", "QO", "An Opera", date="1875-01-01T00:00:00Z", p31s=["Q1344"]),
            _binding("Q1", "QF", "A Film", date="1984-01-01T00:00:00Z", p31s=["Q11424"]),
            _binding("Q1", "QR", "A Radio", date="1955-01-01T00:00:00Z", p31s=["Q2635894"]),
        ])
        _patch_sparql(monkeypatch, payload)
        out = adaptations_for_books(["Q1"])
        years = [a["year"] for a in out["Q1"]]
        assert years == sorted(years)

    def test_missing_year_omitted_and_sorted_last(self, monkeypatch):
        payload = _results([
            _binding("Q1", "QF", "Dated Film", date="1984-01-01T00:00:00Z", p31s=["Q11424"]),
            _binding("Q1", "QN", "Undated Film", p31s=["Q11424"]),  # no date/inception
        ])
        _patch_sparql(monkeypatch, payload)
        out = adaptations_for_books(["Q1"])
        adaptations = out["Q1"]
        # Undated entry has no 'year' key and sorts last.
        assert "year" not in adaptations[-1]
        assert adaptations[-1]["title"] == "Undated Film"
        assert adaptations[0]["year"] == 1984

    def test_inception_fallback_when_no_publication_date(self, monkeypatch):
        payload = _results([
            _binding("Q1", "QF", "A Film", inception="1971-01-01T00:00:00Z", p31s=["Q11424"]),
        ])
        _patch_sparql(monkeypatch, payload)
        out = adaptations_for_books(["Q1"])
        assert out["Q1"][0]["year"] == 1971

    def test_dedup_by_type_title_year(self, monkeypatch):
        # Two distinct work QIDs with identical (type,title,year) → one entry.
        payload = _results([
            _binding("Q1", "QA", "Same Film", date="1984-01-01T00:00:00Z", p31s=["Q11424"]),
            _binding("Q1", "QB", "Same Film", date="1984-01-01T00:00:00Z", p31s=["Q11424"]),
        ])
        _patch_sparql(monkeypatch, payload)
        out = adaptations_for_books(["Q1"])
        assert len(out["Q1"]) == 1

    def test_multi_p31_rows_for_same_work_merge(self, monkeypatch):
        # GROUP_CONCAT normally collapses P31s, but if the endpoint returns
        # the work over multiple rows we still merge P31 + fill year.
        payload = _results([
            _binding("Q1", "QW", "TV Film", date="2000-01-01T00:00:00Z", p31s=["Q11424"]),
            _binding("Q1", "QW", "TV Film", p31s=["Q93204"]),  # television film
        ])
        _patch_sparql(monkeypatch, payload)
        out = adaptations_for_books(["Q1"])
        assert len(out["Q1"]) == 1
        assert out["Q1"][0]["type"] == "tv"  # tv wins over film
        assert out["Q1"][0]["year"] == 2000

    def test_label_equal_to_qid_is_skipped(self, monkeypatch):
        # SERVICE label returns the QID when no label exists — not a title.
        payload = _results([
            _binding("Q1", "QW", "QW", date="2000-01-01T00:00:00Z", p31s=["Q11424"]),
        ])
        _patch_sparql(monkeypatch, payload)
        out = adaptations_for_books(["Q1"])
        assert "Q1" not in out  # nothing usable

    def test_cap_per_book(self, monkeypatch):
        bindings = [
            _binding("Q1", f"QW{i}", f"Film {i:02d}",
                     date=f"19{50 + i:02d}-01-01T00:00:00Z", p31s=["Q11424"])
            for i in range(MAX_ADAPTATIONS_PER_BOOK + 5)
        ]
        _patch_sparql(monkeypatch, _results(bindings))
        out = adaptations_for_books(["Q1"])
        assert len(out["Q1"]) == MAX_ADAPTATIONS_PER_BOOK

    def test_multiple_books(self, monkeypatch):
        payload = _results([
            _binding("Q1", "QF1", "Film One", date="1984-01-01T00:00:00Z", p31s=["Q11424"]),
            _binding("Q2", "QF2", "Film Two", date="1990-01-01T00:00:00Z", p31s=["Q11424"]),
        ])
        _patch_sparql(monkeypatch, payload)
        out = adaptations_for_books(["Q1", "Q2"])
        assert out["Q1"][0]["title"] == "Film One"
        assert out["Q2"][0]["title"] == "Film Two"

    def test_no_qids_returns_empty(self, monkeypatch):
        # Non-Q inputs are dropped before any query.
        out = adaptations_for_books(["", "notaqid", None])
        assert out == {}

    def test_no_results_returns_empty(self, monkeypatch):
        _patch_sparql(monkeypatch, _results([]))
        assert adaptations_for_books(["Q1"]) == {}


class TestBatchFailureContract:
    """adaptations_for_batch must distinguish 'no data' (empty dict) from a
    transient query failure (None) so the enricher can resume correctly."""

    def test_transient_failure_returns_none(self, monkeypatch):
        # _sparql returns None on timeout/429-after-backoff.
        monkeypatch.setattr(wikidata, "_sparql", lambda q: None)
        monkeypatch.setattr(
            wikidata, "cached_fetch", lambda source, key, fetch, **kw: fetch()
        )
        calls = []
        monkeypatch.setattr(
            wikidata, "cache_invalidate",
            lambda source, key: calls.append((source, key)),
        )
        assert adaptations_for_batch(["Q1", "Q2"]) is None
        # The poisoned-negative cache entry is invalidated so a resumed run
        # re-queries rather than trusting a false "no adaptations".
        assert calls and calls[0][0] == "wikidata_adaptations_v1"

    def test_empty_result_returns_empty_dict_not_none(self, monkeypatch):
        # A genuine empty result is a truthy {results:{bindings:[]}} → {}.
        _patch_sparql(monkeypatch, _results([]))
        assert adaptations_for_batch(["Q1"]) == {}

    def test_batch_with_data(self, monkeypatch):
        payload = _results([
            _binding("Q1", "QF", "A Film", date="1984-01-01T00:00:00Z", p31s=["Q11424"]),
        ])
        _patch_sparql(monkeypatch, payload)
        out = adaptations_for_batch(["Q1"])
        assert out == {"Q1": [{"type": "film", "title": "A Film", "year": 1984}]}

    def test_non_q_inputs_dropped(self, monkeypatch):
        assert adaptations_for_batch(["", "x", None]) == {}


class TestSparqlTimeoutHandling:
    """The SPARQL transport must return None on a hung/timed-out endpoint
    rather than blocking — it routes through http_retry.fetch_with_retry,
    which always applies a bounded timeout."""

    def test_timeout_returns_none(self, monkeypatch):
        # fetch_with_retry returns (None, 0, {}) on a network timeout.
        monkeypatch.setattr(wikidata, "fetch_with_retry", lambda url, **kw: (None, 0, {}))
        monkeypatch.setattr(wikidata, "_pace", lambda: None)
        assert wikidata._sparql("SELECT * WHERE { ?s ?p ?o }") is None

    def test_success_parses_json(self, monkeypatch):
        body = b'{"results": {"bindings": []}}'
        monkeypatch.setattr(wikidata, "fetch_with_retry", lambda url, **kw: (body, 200, {}))
        monkeypatch.setattr(wikidata, "_pace", lambda: None)
        assert wikidata._sparql("SELECT * WHERE { ?s ?p ?o }") == {
            "results": {"bindings": []}
        }

    def test_malformed_body_returns_none(self, monkeypatch):
        monkeypatch.setattr(wikidata, "fetch_with_retry", lambda url, **kw: (b"not json", 200, {}))
        monkeypatch.setattr(wikidata, "_pace", lambda: None)
        assert wikidata._sparql("SELECT * WHERE { ?s ?p ?o }") is None

    def test_429_after_budget_capped_retry_then_none(self, monkeypatch):
        # Sustained 429 (fetch_with_retry exhausted its budget, status 429).
        # _sparql does a capped minute-backoff retry then gives up — never
        # loops forever. Stub sleep so the test is fast.
        monkeypatch.setattr(wikidata, "fetch_with_retry", lambda url, **kw: (None, 429, {}))
        monkeypatch.setattr(wikidata, "_pace", lambda: None)
        sleeps = []
        monkeypatch.setattr(wikidata._time, "sleep", lambda s: sleeps.append(s))
        assert wikidata._sparql("SELECT * WHERE { ?s ?p ?o }") is None
        assert 0 < len(sleeps) <= wikidata.SPARQL_MAX_429_RETRIES
