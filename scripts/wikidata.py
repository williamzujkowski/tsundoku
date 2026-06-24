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
from http_cache import cached_fetch, invalidate as cache_invalidate
from http_retry import fetch_with_retry


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


# How many times to retry a 429 before giving up. WDQS occasionally enters
# an aggressive "1 request / minute" mode during outages; a few patient
# retries that honor Retry-After let a batch eventually succeed instead of
# being skipped (and re-queried only on a later run).
SPARQL_MAX_429_RETRIES = 5


def _sparql(query: str) -> dict | None:
    """Execute a SPARQL query, return parsed JSON or None on error.

    Routes the request through ``http_retry.fetch_with_retry`` so it always
    has a bounded socket timeout (``REQUEST_TIMEOUT``) and honors Retry-After
    / exponential backoff on 429/503 — a slow or non-responding WDQS endpoint
    returns ``None`` instead of blocking forever (the raw ``urlopen`` path
    could stall indefinitely on a trickled response body, hanging the scan).

    Respects the inter-call pacing. ``fetch_with_retry`` does its own
    429-aware retries; we leave SPARQL_MAX_429_RETRIES for the dedicated
    minute-backoff outage path below as a final, capped fallback. Non-429
    errors and parse failures return None.
    """
    url = f"{SPARQL_URL}?query={quote_plus(query)}&format=json"
    headers = {
        "User-Agent": WIKIDATA_UA,
        "Accept": "application/sparql-results+json",
    }
    for attempt in range(SPARQL_MAX_429_RETRIES + 1):
        _pace()
        body, status, _resp_headers = fetch_with_retry(
            url,
            user_agent=WIKIDATA_UA,
            timeout=REQUEST_TIMEOUT,
            extra_headers=headers,
        )
        if body is not None:
            try:
                return json.loads(body)
            except (json.JSONDecodeError, ValueError):
                return None
        # body is None → permanent/exhausted failure. For a sustained-outage
        # 429 (status 429 after fetch_with_retry burned its budget), do a
        # capped minute-level backoff and retry the whole request; otherwise
        # give up immediately.
        if status == 429 and attempt < SPARQL_MAX_429_RETRIES:
            _time.sleep(SPARQL_BACKOFF_429_S)
            continue
        return None
    return None


def _qids_by_p648(keys: list[str], olid_path_prefix: str) -> dict[str, str]:
    """Shared helper: map OL IDs → QIDs via P648, batched. Returns {f'{prefix}{id}': qid}."""
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
        cache_key = f"qids_by_p648:{olid_path_prefix}:{','.join(sorted(batch))}"
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
                out[f"{olid_path_prefix}{olid}"] = qid
    return out


def qids_by_ol_work_keys(keys: Iterable[str]) -> dict[str, str]:
    """Map OL work keys → Wikidata QIDs via P648. Returns {/works/OL...W: Q...}."""
    cleaned = [
        k.replace("/works/", "") if k.startswith("/works/") else k
        for k in keys
    ]
    cleaned = [k for k in cleaned if k.startswith("OL") and k.endswith("W")]
    return _qids_by_p648(list(set(cleaned)), olid_path_prefix="/works/")


def qids_by_ol_author_keys(keys: Iterable[str]) -> dict[str, str]:
    """Map OL author keys → Wikidata QIDs via P648. Returns {/authors/OL...A: Q...}."""
    cleaned = [
        k.replace("/authors/", "") if k.startswith("/authors/") else k
        for k in keys
    ]
    cleaned = [k for k in cleaned if k.startswith("OL") and k.endswith("A")]
    return _qids_by_p648(list(set(cleaned)), olid_path_prefix="/authors/")


def enwiki_title(entity: dict | None, qid: str) -> str | None:
    """Return the English Wikipedia article title for an entity, or None.

    Used to bridge from a Wikidata QID (resolved via P648 from OL author
    keys) back to a curated Wikipedia article — letting downstream
    enrichers fetch the REST summary by exact title rather than gambling
    on a by-name search.
    """
    if not entity or not qid:
        return None
    sitelinks = (((entity.get("entities") or {}).get(qid) or {}).get("sitelinks")) or {}
    enwiki = sitelinks.get("enwiki") or {}
    title = enwiki.get("title")
    return title if isinstance(title, str) and title else None


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


def fields_for_author(qid: str, entity: dict) -> dict:
    """Convert a Wikidata author entity into tsundoku author schema fields.

    Pulls (in order of property):
      P27   (country of citizenship) → nationality (ISO 3166-1 alpha-2)
      P742  (pseudonym)              → alternate_names (string list)
      P135  (movement)               → movements (label list, needs resolution)
      P166  (awards received)        → awards [{name, year}]
      P214  (VIAF ID)                → viaf_id
      P648  (OL author key)          → ol_author_key (cross-validation)

    Birth/death dates (P569, P570) are intentionally NOT pulled — we already
    get those from OL's enrich-authors.py and don't want to clobber them.
    """
    out: dict = {"wikidata_qid": qid}

    # Nationality — Wikidata gives QIDs for countries; map to ISO 3166-1 alpha-2.
    # Common-country subset; expanded as we encounter unmapped QIDs.
    COUNTRY_QID_TO_ISO2 = {
        "Q145": "GB", "Q21": "GB",     # England → GB
        "Q30": "US", "Q35": "DK", "Q34": "SE",
        "Q183": "DE", "Q142": "FR", "Q38": "IT", "Q29": "ES",
        "Q159": "RU", "Q34266": "RU", # Russian Empire → RU
        "Q17": "JP", "Q148": "CN", "Q668": "IN", "Q884": "KR",
        "Q40": "AT", "Q31": "BE", "Q32": "LU", "Q39": "CH",
        "Q33": "FI", "Q20": "NO", "Q43": "TR", "Q41": "GR",
        "Q45": "PT", "Q55": "NL", "Q36": "PL", "Q37": "LT",
        "Q211": "LV", "Q191": "EE", "Q224": "HR", "Q403": "RS",
        "Q214": "SK", "Q213": "CZ", "Q28": "HU", "Q218": "RO",
        "Q219": "BG", "Q189": "IS", "Q230": "GE", "Q227": "AZ",
        "Q399": "AM", "Q228": "AD", "Q347": "LI", "Q235": "MC",
        "Q16": "CA", "Q414": "AR", "Q155": "BR", "Q298": "CL",
        "Q717": "VE", "Q739": "CO", "Q794": "IR", "Q801": "IL",
        "Q804": "PA", "Q733": "PY", "Q736": "EC", "Q750": "BO",
        "Q419": "PE", "Q813": "KZ", "Q833": "MY", "Q865": "TW",
        "Q869": "TH", "Q881": "VN", "Q884": "KR", "Q928": "PH",
        "Q924": "ZW", "Q953": "ZM", "Q1014": "LR", "Q1029": "MZ",
        "Q1037": "RW", "Q1041": "SN", "Q1045": "SO", "Q258": "ZA",
        "Q1049": "SD", "Q117": "GH", "Q1009": "CM", "Q1019": "MG",
        "Q1027": "MU", "Q967": "BI", "Q986": "ER", "Q1008": "CI",
        "Q1028": "MA", "Q1033": "NG", "Q414": "AR", "Q408": "AU",
        "Q664": "NZ", "Q34020": "AU",  # Aboriginal Aus. → AU
    }
    nat_codes = []
    seen = set()
    for stmt in _statements(entity, qid, "P27"):
        country_qid = _value_id(stmt)
        code = COUNTRY_QID_TO_ISO2.get(country_qid)
        if code and code not in seen:
            seen.add(code)
            nat_codes.append(code)
    if nat_codes:
        out["nationality"] = nat_codes

    # Pseudonyms / alternate names (P742) — these are simple string values.
    alt_names = []
    for stmt in _statements(entity, qid, "P742"):
        v = ((stmt.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if isinstance(v, str) and v not in alt_names:
            alt_names.append(v)
    if alt_names:
        out["alternate_names"] = alt_names

    # Movements (P135) — record QIDs; caller resolves to labels.
    movement_qids = []
    for stmt in _statements(entity, qid, "P135"):
        mq = _value_id(stmt)
        if mq and mq not in movement_qids:
            movement_qids.append(mq)
    if movement_qids:
        out["_movement_qids"] = movement_qids

    # Awards (P166) with year qualifier P585
    awards = []
    for stmt in _statements(entity, qid, "P166"):
        award_qid = _value_id(stmt)
        if not award_qid:
            continue
        year = None
        year_q = (stmt.get("qualifiers") or {}).get("P585") or []
        if year_q:
            t = ((year_q[0] or {}).get("datavalue") or {}).get("value")
            if isinstance(t, dict):
                y, _ = parse_wikidata_year(t)
                year = y
        awards.append({"_qid": award_qid, **({"year": year} if year else {})})
    if awards:
        out["_awards"] = awards

    # VIAF ID (P214)
    for stmt in _statements(entity, qid, "P214"):
        v = ((stmt.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if isinstance(v, str):
            out["viaf_id"] = v
            break

    # OL author key (P648) — cross-validate
    for stmt in _statements(entity, qid, "P648"):
        v = ((stmt.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if isinstance(v, str) and v.endswith("A"):
            out["ol_author_key"] = f"/authors/{v}"
            break

    return out


# ---------------------------------------------------------------------------
# Adaptations (P144 "based on") — issue #184
# ---------------------------------------------------------------------------

# The book schema enum is {film, tv, stage, radio, opera, other}. We classify
# the adaptation's P31 (instance-of) QID into one of those buckets. An
# unmapped P31 (or no P31) maps to 'other' so we never emit an out-of-enum
# value the content collection would reject. Conflicts are resolved by the
# fixed priority in _classify_adaptation_types (tv > film > opera > stage >
# radio) — e.g. a "television film" lands deterministically on 'tv'.
P31_TYPE_MAP: dict[str, str] = {
    # film
    "Q11424": "film", "Q24862": "film", "Q202866": "film", "Q24869": "film",
    "Q229390": "film", "Q18011172": "film", "Q130232": "film",
    "Q1054574": "film", "Q959790": "film", "Q1361932": "film",  # comedy film
    "Q645928": "film",  # epic film
    # tv (television films map to tv)
    "Q5398426": "tv", "Q1259759": "tv", "Q581714": "tv", "Q63952888": "tv",
    "Q1107": "tv", "Q117467246": "tv", "Q15416": "tv", "Q21191270": "tv",
    "Q526877": "tv", "Q1366112": "tv", "Q220898": "tv", "Q93204": "tv",
    "Q506240": "tv", "Q5398427": "tv",  # television drama series
    # stage
    "Q25379": "stage", "Q2743": "stage", "Q43099500": "stage", "Q11635": "stage",
    "Q188451": "stage", "Q5398472": "stage", "Q7777573": "stage", "Q7777570": "stage",
    "Q7777577": "stage",  # theatrical adaptation variants
    # radio
    "Q2635894": "radio", "Q1320047": "radio", "Q14406742": "radio", "Q3736046": "radio",
    # opera
    "Q1344": "opera", "Q1278123": "opera",
}

# Bucket for any P31 not in the map but which is still clearly a creative work
# we want to keep. Currently we keep everything (unmapped → 'other'); the cap
# and dedup keep volume sane.
MAX_ADAPTATIONS_PER_BOOK = 12

# Books per P144 SPARQL request. Kept small (20) so a single batch's query
# stays cheap and well under the 60s endpoint timeout even during WDQS load —
# a heavy 40-book fan-out across P144/P31/P577 was a hang risk.
ADAPTATIONS_BATCH_SIZE = 20


def _classify_adaptation_types(p31_qids: list[str]) -> str:
    """Pick a schema type from a work's instance-of QIDs.

    A work can be instance-of several classes (e.g. both 'film' and 'drama
    film'). We prefer the most specific recognizable medium, with a fixed
    priority so a "television film" lands on 'tv' deterministically. Unknown
    or empty → 'other'.
    """
    matched = [P31_TYPE_MAP[q] for q in p31_qids if q in P31_TYPE_MAP]
    if not matched:
        return "other"
    # Priority order when a work is tagged with multiple media classes.
    for pref in ("tv", "film", "opera", "stage", "radio"):
        if pref in matched:
            return pref
    return "other"


def adaptations_for_books(qids: Iterable[str]) -> dict[str, list[dict]]:
    """Map book QIDs → list of {type, title, year?} adaptations via P144.

    For each adaptation work `?w` where `?w wdt:P144 wd:<book>`, we pull:
      * its English label (title)
      * a year from P577 (publication date) or, failing that, P571 (inception)
      * its P31 instance-of QIDs, classified into the schema type enum

    Queries are batched with a VALUES ?book clause (~40 books/request) to
    stay well under the 60s SPARQL timeout and be rate-limit friendly.
    Results are cached via http_cache. Each book's list is deduped by
    (type, title, year), sorted by year (None last), and capped.
    """
    cleaned = sorted({q for q in qids if q and q.startswith("Q")})
    if not cleaned:
        return {}

    out: dict[str, list[dict]] = {}
    batch_size = ADAPTATIONS_BATCH_SIZE
    for start in range(0, len(cleaned), batch_size):
        batch = cleaned[start:start + batch_size]
        batch_result = adaptations_for_batch(batch)
        if batch_result is None:
            continue  # transient failure for this batch — skip its books
        out.update(batch_result)
    return out


def adaptations_for_batch(batch: list[str]) -> dict[str, list[dict]] | None:
    """Query one batch of book QIDs for P144 adaptations.

    Returns a dict {book_qid: [{type, title, year?}, ...]} for the books in
    `batch` that have adaptations (books with none are simply absent), or
    ``None`` when the query failed transiently (timeout / network / 429 after
    backoff). The None signal lets the caller leave those books un-scanned so
    a resumed run re-queries them, instead of recording them as "no data".
    """
    batch = [q for q in batch if q and q.startswith("Q")]
    if not batch:
        return {}

    values = " ".join(f"wd:{q}" for q in batch)
    # One row per (work, P31). We fetch the English label with a direct
    # rdfs:label + LANG() filter rather than the wikibase:label SERVICE:
    # the SERVICE combined with GROUP BY makes this query 100x+ slower
    # (it can blow the 60s endpoint timeout for a 40-book batch). We
    # aggregate the multiple-P31 rows back into one work in Python below.
    query = f"""
    SELECT ?book ?work ?workLabel ?date ?inception ?p31 WHERE {{
      VALUES ?book {{ {values} }}
      ?work wdt:P144 ?book .
      OPTIONAL {{ ?work wdt:P31 ?p31 . }}
      OPTIONAL {{ ?work wdt:P577 ?date . }}
      OPTIONAL {{ ?work wdt:P571 ?inception . }}
      ?work rdfs:label ?workLabel . FILTER(LANG(?workLabel) = "en")
    }}
    """
    cache_key = f"adaptations:{','.join(sorted(batch))}"
    data = cached_fetch(
        "wikidata_adaptations_v1",
        cache_key,
        lambda q=query: _sparql(q),
    )
    if data is None:
        # _sparql returns None only on a transient failure (timeout, network,
        # or 429 after backoff) — never for a genuine empty result (that's a
        # truthy {results:{bindings:[]}}). Don't let the negative get cached
        # as a false "no adaptations": invalidate so a resumed run re-queries.
        cache_invalidate("wikidata_adaptations_v1", cache_key)
        return None

    # Accumulate raw rows per book: {book_qid: {work_qid: {title, year, p31s}}}
    raw: dict[str, dict[str, dict]] = {}
    for b in (data.get("results", {}) or {}).get("bindings", []) or []:
        book_qid = b.get("book", {}).get("value", "").rsplit("/", 1)[-1]
        work_qid = b.get("work", {}).get("value", "").rsplit("/", 1)[-1]
        if not book_qid or not work_qid:
            continue
        label = b.get("workLabel", {}).get("value")
        # No English label → can't form a usable title; skip the row.
        if not label or label == work_qid:
            continue
        year = _year_from_iso(b.get("date", {}).get("value")) \
            or _year_from_iso(b.get("inception", {}).get("value"))
        p31 = b.get("p31", {}).get("value", "")
        p31_qid = p31.rsplit("/", 1)[-1] if p31 else None

        book_bucket = raw.setdefault(book_qid, {})
        existing = book_bucket.get(work_qid)
        if existing is None:
            book_bucket[work_qid] = {
                "title": label,
                "year": year,
                "p31s": [p31_qid] if p31_qid else [],
            }
        else:
            # Another P31 row for the same work — accumulate P31s and
            # fill a missing year if this row carries one.
            if p31_qid and p31_qid not in existing["p31s"]:
                existing["p31s"].append(p31_qid)
            if existing.get("year") is None and year is not None:
                existing["year"] = year

    # Reduce raw rows to clean, deduped, sorted, capped adaptation lists.
    out: dict[str, list[dict]] = {}
    for book_qid, works in raw.items():
        adaptations = []
        seen: set[tuple] = set()
        for work in works.values():
            entry: dict = {
                "type": _classify_adaptation_types(work["p31s"]),
                "title": work["title"],
            }
            if work.get("year") is not None:
                entry["year"] = work["year"]
            key = (entry["type"], entry["title"], entry.get("year"))
            if key in seen:
                continue
            seen.add(key)
            adaptations.append(entry)
        # Sort by year (None last), then title for stability.
        adaptations.sort(key=lambda a: (a.get("year") is None, a.get("year") or 0, a["title"]))
        if adaptations:
            out[book_qid] = adaptations[:MAX_ADAPTATIONS_PER_BOOK]
    return out


def _year_from_iso(value: str | None) -> int | None:
    """Extract a year int from a SPARQL xsd:dateTime literal like
    '1965-08-01T00:00:00Z' or '-0428-...'. Returns None when unparseable."""
    if not value or not isinstance(value, str):
        return None
    sign = -1 if value.startswith("-") else 1
    body = value.lstrip("+-")
    year_str = body.split("-", 1)[0]
    try:
        return int(year_str) * sign
    except ValueError:
        return None


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
