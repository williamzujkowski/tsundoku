"""Wikidata SPARQL helpers for enrichment scripts.

Uses Wikidata's public SPARQL endpoint to look up structured data about
books and authors. The endpoint enforces:

  • A 60-second query timeout (so we batch carefully).
  • Polite usage: User-Agent must include contact info per Wikidata policy.
  • Up to ~5 concurrent requests / IP — we serialise.

This module is built around batch lookups by Open Library ID (P648 for books,
P648 also for authors via the author work-key chain). One batch call per
~50 IDs trades cleanly under the 60s timeout. Responses are cached via
http_cache so re-runs are free.

Public functions:

    qids_by_ol_work_keys(keys)        # dict: ol_key → qid
    book_first_edition(qid)           # dict: P577, P123, P407, etc.
    author_demographics(qid)          # dict: P27, P135, P166, etc.

The fields_for_book and fields_for_author wrappers convert a Wikidata
response into the schema fields tsundoku stores (first_published,
original_language, publisher, awards, series, etc.).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus
from urllib.request import urlopen, Request

sys.path.insert(0, str(Path(__file__).parent))

from enrichment_config import USER_AGENT
from http_cache import cached_fetch


SPARQL_URL = "https://query.wikidata.org/sparql"
ENTITY_URL = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
REQUEST_TIMEOUT = 60
BATCH_SIZE = 50

# Wikidata's SPARQL endpoint enforces 2 RPS. We sleep 0.6s between SPARQL
# calls (well below cap) and back off aggressively on 429 with Retry-After.
SPARQL_MIN_INTERVAL_S = 0.6
SPARQL_BACKOFF_429_S = 60

# Polite UA per Wikidata policy — must include contact info.
WIKIDATA_UA = f"{USER_AGENT.split(' ')[0]} (mailto:grenlan@gmail.com)"

# Module-level pacing (single-process; process-wide last-call timestamp)
import time as _time
_last_call_ts = 0.0


def _pace() -> None:
    global _last_call_ts
    now = _time.monotonic()
    delta = now - _last_call_ts
    if delta < SPARQL_MIN_INTERVAL_S:
        _time.sleep(SPARQL_MIN_INTERVAL_S - delta)
    _last_call_ts = _time.monotonic()


def _sparql(query: str) -> dict | None:
    """Execute a SPARQL query, return parsed JSON or None on error.

    Respects 2 RPS limit and the Retry-After header on 429.
    """
    _pace()
    url = f"{SPARQL_URL}?query={quote_plus(query)}&format=json"
    req = Request(
        url,
        headers={
            "User-Agent": WIKIDATA_UA,
            "Accept": "application/sparql-results+json",
        },
    )
    try:
        with urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            return json.loads(resp.read())
    except HTTPError as e:
        if e.code == 429:
            retry = e.headers.get("Retry-After")
            wait_s = SPARQL_BACKOFF_429_S
            try:
                wait_s = max(wait_s, int(retry)) if retry else wait_s
            except (TypeError, ValueError):
                pass
            _time.sleep(wait_s)
            # One retry after the backoff
            _pace()
            try:
                with urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                    return json.loads(resp.read())
            except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
                return None
        return None
    except (URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None


def qids_by_ol_work_keys(keys: Iterable[str]) -> dict[str, str]:
    """Map OL work keys → Wikidata QIDs in batches.

    Looks up `wdt:P648` (Open Library ID). Not every book has one, but
    famous works tend to. Returns {ol_key: qid} for matches only.
    """
    keys = [k.replace("/works/", "") if k.startswith("/works/") else k
            for k in keys]
    keys = [k for k in keys if k.startswith("OL") and k.endswith("W")]

    out: dict[str, str] = {}
    for batch_start in range(0, len(keys), BATCH_SIZE):
        batch = keys[batch_start:batch_start + BATCH_SIZE]
        values = " ".join(f'"{k}"' for k in batch)
        query = f"""
        SELECT ?item ?olid WHERE {{
          VALUES ?olid {{ {values} }}
          ?item wdt:P648 ?olid .
        }}
        """
        cache_key = f"qids_by_olw:{','.join(sorted(batch))}"
        data = cached_fetch(
            "wikidata_sparql_v1",
            cache_key,
            lambda q=query: _sparql(q),
        )
        if not data:
            continue
        for binding in (data.get("results", {}) or {}).get("bindings", []) or []:
            qid = binding.get("item", {}).get("value", "").rsplit("/", 1)[-1]
            olid = binding.get("olid", {}).get("value")
            if qid and olid:
                out[f"/works/{olid}"] = qid
    return out


def fetch_entity(qid: str) -> dict | None:
    """Fetch a Wikidata entity by QID. Cached."""
    if not qid or not qid.startswith("Q"):
        return None
    url = ENTITY_URL.format(qid=qid)
    cache_key = f"entity:{qid}"

    def _fetch() -> dict | None:
        _pace()
        req = Request(url, headers={"User-Agent": WIKIDATA_UA})
        try:
            with urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                return json.loads(resp.read())
        except HTTPError as e:
            if e.code == 429:
                retry = e.headers.get("Retry-After")
                wait_s = SPARQL_BACKOFF_429_S
                try:
                    wait_s = max(wait_s, int(retry)) if retry else wait_s
                except (TypeError, ValueError):
                    pass
                _time.sleep(wait_s)
            return None
        except (URLError, TimeoutError, OSError, json.JSONDecodeError):
            return None

    return cached_fetch("wikidata_entity_v1", cache_key, _fetch)


# ---------------------------------------------------------------------------
# Property extraction
# ---------------------------------------------------------------------------

def _statements(entity: dict, qid: str, prop: str) -> list[dict]:
    """Get all statements for a property, or empty list."""
    return ((entity.get("entities") or {}).get(qid) or {}).get("claims", {}).get(prop, [])


def _value_id(stmt: dict) -> str | None:
    return ((stmt.get("mainsnak") or {}).get("datavalue") or {}).get("value", {}).get("id")


def _value_string(stmt: dict) -> str | None:
    v = ((stmt.get("mainsnak") or {}).get("datavalue") or {}).get("value")
    return v if isinstance(v, str) else None


def _value_time(stmt: dict) -> dict | None:
    """A Wikidata time value: {time: '+1949-06-08T00:00:00Z', precision: 11, ...}."""
    v = ((stmt.get("mainsnak") or {}).get("datavalue") or {}).get("value")
    return v if isinstance(v, dict) and "time" in v else None


def _qualifier_id(stmt: dict, prop: str) -> str | None:
    """Pull a qualifier QID from a statement (e.g. P1545 series position)."""
    quals = (stmt.get("qualifiers") or {}).get(prop) or []
    if not quals:
        return None
    return ((quals[0] or {}).get("datavalue") or {}).get("value", {}).get("id")


def _qualifier_amount(stmt: dict, prop: str) -> int | None:
    quals = (stmt.get("qualifiers") or {}).get(prop) or []
    if not quals:
        return None
    v = ((quals[0] or {}).get("datavalue") or {}).get("value")
    if isinstance(v, dict) and "amount" in v:
        try:
            return int(v["amount"])
        except (TypeError, ValueError):
            return None
    return None


def parse_wikidata_year(time_value: dict | None) -> tuple[int | None, bool]:
    """Wikidata time → (year, circa).

    Wikidata time format: {time: '+1949-06-08T00:00:00Z', precision: 9-11, ...}
    Precision 9 = year, 10 = month, 11 = day. Lower precisions (5-8) mean
    century/millennium and we treat as circa.
    """
    if not time_value:
        return (None, False)
    t = time_value.get("time", "")
    if not t:
        return (None, False)
    # Strip the leading sign for parsing; preserve for BCE
    sign = -1 if t.startswith("-") else 1
    body = t.lstrip("+-")
    # First field is the year (may have leading zeros)
    year_str = body.split("-", 1)[0]
    try:
        year = int(year_str) * sign
    except ValueError:
        return (None, False)
    precision = time_value.get("precision", 9)
    circa = precision is not None and precision < 9  # less than year-precision
    return (year, circa)


def fields_for_book(qid: str, entity: dict) -> dict:
    """Convert a Wikidata book entity into tsundoku schema fields.

    Pulls (in order of property):
      P1476 (title)         → original_title
      P407  (language)      → original_language (ISO 639-3)
      P123  (publisher)     → original_publisher
      P577  (publication date) → first_published, first_published_circa
      P166  (award received) → awards [{name, year}]
      P179  (part of series) → series.name
        +P1545 (qualifier: series ordinal)
      P50   (author)        — not stored; informational only
    """
    out: dict = {"wikidata_qid": qid}

    # Title — pick the English value if present
    titles = _statements(entity, qid, "P1476")
    for stmt in titles:
        v = ((stmt.get("mainsnak") or {}).get("datavalue") or {}).get("value", {})
        if isinstance(v, dict) and v.get("language") == "en" and v.get("text"):
            out["original_title"] = v["text"]
            break
    if "original_title" not in out and titles:
        v = ((titles[0].get("mainsnak") or {}).get("datavalue") or {}).get("value", {})
        if isinstance(v, dict) and v.get("text"):
            out["original_title"] = v["text"]

    # Language — Wikidata gives QID; we want ISO 639-3.
    # Common languages → codes (subset; expand as we encounter more).
    LANG_QID_TO_CODE = {
        "Q1860": "eng", "Q150": "fre", "Q188": "ger", "Q1321": "spa",
        "Q652": "ita", "Q5146": "por", "Q7737": "rus", "Q5287": "jpn",
        "Q7850": "chi", "Q9176": "kor", "Q13955": "ara", "Q9288": "heb",
        "Q397": "lat", "Q35497": "grc", "Q9129": "gre",
        "Q809": "pol", "Q9027": "swe", "Q9043": "nor", "Q9035": "dan",
        "Q1412": "fin", "Q7411": "dut", "Q9056": "cze", "Q9067": "hun",
        "Q256": "tur", "Q1568": "hin", "Q11059": "san",
        "Q9168": "per", "Q9199": "vie", "Q9217": "tha",
        "Q8641": "yid", "Q294": "ice", "Q7913": "ron", "Q8798": "ukr",
        "Q7026": "cat",
    }
    langs = _statements(entity, qid, "P407")
    for stmt in langs:
        lang_qid = _value_id(stmt)
        code = LANG_QID_TO_CODE.get(lang_qid)
        if code:
            out["original_language"] = code
            break

    # Publisher — name comes from the linked entity's label, which we'd need
    # an extra fetch for. For now record QID; Phase B v2 can resolve labels.
    publishers = _statements(entity, qid, "P123")
    if publishers:
        pub_qid = _value_id(publishers[0])
        if pub_qid:
            out["_publisher_qid"] = pub_qid  # underscored = pre-resolved field

    # Publication date — most authoritative source for first_published.
    dates = _statements(entity, qid, "P577")
    earliest_year: int | None = None
    earliest_circa = False
    for stmt in dates:
        year, circa = parse_wikidata_year(_value_time(stmt))
        if year is not None:
            if earliest_year is None or year < earliest_year:
                earliest_year = year
                earliest_circa = circa
    if earliest_year is not None:
        out["first_published"] = earliest_year
        out["first_published_circa"] = earliest_circa

    # Awards (P166)
    awards = _statements(entity, qid, "P166")
    award_list = []
    for stmt in awards:
        award_qid = _value_id(stmt)
        if not award_qid:
            continue
        # Year qualifier P585 (point in time)
        year_q = (stmt.get("qualifiers") or {}).get("P585") or []
        year = None
        if year_q:
            t = ((year_q[0] or {}).get("datavalue") or {}).get("value")
            if isinstance(t, dict):
                y, _ = parse_wikidata_year(t)
                year = y
        award_list.append({"_qid": award_qid, **({"year": year} if year else {})})
    if award_list:
        out["_awards"] = award_list

    # Series (P179) with ordinal P1545
    series_stmts = _statements(entity, qid, "P179")
    if series_stmts:
        first = series_stmts[0]
        series_qid = _value_id(first)
        position = None
        ord_qual = (first.get("qualifiers") or {}).get("P1545") or []
        if ord_qual:
            try:
                position = int(((ord_qual[0] or {}).get("datavalue") or {}).get("value"))
            except (TypeError, ValueError):
                position = None
        if series_qid:
            entry: dict = {"_qid": series_qid}
            if position is not None:
                entry["position"] = position
            out["_series"] = entry

    return out


def resolve_qid_labels(qids: Iterable[str], lang: str = "en") -> dict[str, str]:
    """Batch-resolve QIDs to English labels (one extra SPARQL call)."""
    qids = [q for q in qids if q and q.startswith("Q")]
    if not qids:
        return {}
    out: dict[str, str] = {}
    for batch_start in range(0, len(qids), BATCH_SIZE):
        batch = qids[batch_start:batch_start + BATCH_SIZE]
        values = " ".join(f"wd:{q}" for q in batch)
        query = f"""
        SELECT ?item ?itemLabel WHERE {{
          VALUES ?item {{ {values} }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{lang}" }}
        }}
        """
        cache_key = f"labels:{','.join(sorted(batch))}:{lang}"
        data = cached_fetch(
            "wikidata_labels_v1",
            cache_key,
            lambda q=query: _sparql(q),
        )
        if not data:
            continue
        for b in (data.get("results", {}) or {}).get("bindings", []) or []:
            qid = b.get("item", {}).get("value", "").rsplit("/", 1)[-1]
            label = b.get("itemLabel", {}).get("value")
            if qid and label and not label.startswith("Q"):
                out[qid] = label
    return out
