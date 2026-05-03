"""Pluggable enrichment sources for author bio / photo gap-filling.

Each function takes minimal identifying info (name, OLID, etc.) and returns
a dict of fields ready to be additive-merged into an author JSON record.
Functions return {} on miss / network error — never raise.

All HTTP goes through `http_cache.cached_fetch` (#91) so re-runs are cheap.
"""

import json
import re
import sys
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote, quote_plus
from urllib.request import urlopen, Request

sys.path.insert(0, str(Path(__file__).parent))

from enrichment_config import USER_AGENT
from http_cache import cached_fetch


HTTP_TIMEOUT = 15


def _fetch_json(url: str) -> Optional[dict]:
    """One-shot JSON GET with the standard User-Agent. Returns None on any failure."""
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return json.loads(resp.read())
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------------------
# Open Library author page (richer than search.json)
# ---------------------------------------------------------------------------

def _olid_from_url(url: str) -> Optional[str]:
    """Extract OLxxxxxA from an open_library_url like 'https://openlibrary.org/authors/OL26320A'."""
    m = re.search(r"(OL\d+A)", url or "")
    return m.group(1) if m else None


def _search_olid(name: str) -> Optional[str]:
    """Use OL's search.json to find an OLID for a name we don't have one for."""
    url = f"https://openlibrary.org/search/authors.json?q={quote_plus(name)}"
    data = cached_fetch("open_library", f"search:{name}", lambda: _fetch_json(url), url=url)
    if not data:
        return None
    docs = data.get("docs") or []
    if not docs:
        return None
    return docs[0].get("key")  # already in OLxxxxxA form


def from_open_library_author_page(*, olid: Optional[str] = None, name: Optional[str] = None) -> dict:
    """Fetch an Open Library author page; richer than search results.

    Caller can pass an OLID directly (preferred) or a name (slower — needs a search first).
    Returns a dict of populated fields, or {} on miss.
    """
    if not olid and name:
        olid = _search_olid(name)
    if not olid:
        return {}

    url = f"https://openlibrary.org/authors/{olid}.json"
    data = cached_fetch("open_library_author", olid, lambda: _fetch_json(url), url=url)
    if not data:
        return {}

    out: dict = {}

    # bio is sometimes a string, sometimes {"type": "/type/text", "value": "..."}
    bio = data.get("bio")
    if isinstance(bio, dict):
        bio = bio.get("value")
    if bio and isinstance(bio, str) and bio.strip():
        out["bio"] = bio.strip()

    photos = data.get("photos") or []
    if photos and isinstance(photos[0], int) and photos[0] > 0:
        out["photo_url"] = f"https://covers.openlibrary.org/a/id/{photos[0]}-M.jpg"

    out["open_library_url"] = f"https://openlibrary.org/authors/{olid}"

    # Birth/death — OL returns strings like "1871-12-26" or "1871"
    for src, dst in (("birth_date", "birth_year"), ("death_date", "death_year")):
        raw = data.get(src) or ""
        m = re.search(r"\b(\d{4})\b", str(raw))
        if m:
            out[dst] = int(m.group(1))

    return out


# ---------------------------------------------------------------------------
# Wikipedia REST summary — bio + thumbnail + canonical URL
# ---------------------------------------------------------------------------

_YEAR_RANGE = re.compile(r"\((\d{4})\s*[-–]\s*(\d{4})\)")
_BORN_ONLY = re.compile(r"\(born\s+.*?(\d{4})\)", re.I)

# Wikipedia REST returns the most relevant article when there's no exact
# match for a name — often a book/song/film the person wrote, not the
# person. The `description` field reliably names the article kind:
# "novel by X", "1987 book", "American film", etc. Reject those.
_WORK_DESC = re.compile(
    r"\b(novel|book|short\s*story|memoir|essay|treatise|play|poem|"
    r"film|movie|song|album|musical|opera|"
    r"television|TV\s*(?:series|show|episode)|manga|anime|"
    r"video\s*game|comic(?:\s*book)?|graphic\s*novel|"
    r"manuscript|edition|publication|magazine|newspaper|periodical|"
    r"family\s*name|surname|given\s*name|disambiguation|species|genus|"
    r"album\s*by|song\s*by|film\s*by|book\s*by)\b",
    re.I,
)


def from_wikipedia(*, name: str) -> dict:
    """Fetch the Wikipedia REST summary for a person.

    Returns whatever fields are usable: bio (extract), photo_url
    (originalimage > thumbnail.source, upscaled), wikipedia_url, and
    birth_year/death_year extracted from the lede when available.

    Returns {} for:
      * disambiguation pages
      * articles whose `description` identifies them as a work (novel,
        film, song…) or as a name/category — these are returned by the
        REST API when an obscure author has no article of their own and
        Wikipedia auto-redirects to a related article instead.
    """
    if not name:
        return {}
    encoded = quote(name.replace(" ", "_"), safe="")
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
    data = cached_fetch("wikipedia", name, lambda: _fetch_json(url), url=url)
    if not data or data.get("type") == "disambiguation":
        return {}

    description = (data.get("description") or "").strip()
    if description and _WORK_DESC.search(description):
        return {}

    out: dict = {}

    extract = data.get("extract")
    if extract and isinstance(extract, str) and len(extract.strip()) > 50:
        out["bio"] = extract.strip()

    # Prefer the full-resolution originalimage; fall back to the upscaled thumbnail
    img = (data.get("originalimage") or {}).get("source")
    if not img:
        thumb = (data.get("thumbnail") or {}).get("source")
        if thumb:
            # Wikipedia thumb URLs look like .../NNNpx-... — ask for 400px
            img = re.sub(r"/\d+px-", "/400px-", thumb)
    if img and "wiki" in img.lower():
        out["photo_url"] = img

    desktop = (data.get("content_urls") or {}).get("desktop") or {}
    page_url = desktop.get("page")
    if page_url:
        out["wikipedia_url"] = page_url

    # Years: try the curated `description` field first ("Italian author
    # (1923–1985)") — it's short and almost always names the lifespan
    # cleanly. The extract often lists work-publication ranges that look
    # the same and would otherwise win the regex.
    desc = data.get("description") or ""
    m = _YEAR_RANGE.search(desc) or _YEAR_RANGE.search(extract or "")
    if m:
        out["birth_year"] = int(m.group(1))
        out["death_year"] = int(m.group(2))
    else:
        m = _BORN_ONLY.search(desc) or _BORN_ONLY.search(extract or "")
        if m:
            out["birth_year"] = int(m.group(1))

    return out


# ---------------------------------------------------------------------------
# Wikidata (description + image — last-mile fallback)
# ---------------------------------------------------------------------------

def _wikidata_search(name: str) -> Optional[str]:
    """Find a Wikidata Q-id for a person by name."""
    url = (
        "https://www.wikidata.org/w/api.php?action=wbsearchentities"
        f"&search={quote_plus(name)}&format=json&language=en&limit=3"
    )
    data = cached_fetch("wikidata_search", name, lambda: _fetch_json(url), url=url)
    if not data:
        return None
    results = data.get("search") or []
    # Prefer the first result whose description contains "writer", "author", "novelist", "philosopher",
    # etc. Avoids matching same-name disambiguations to football players.
    keywords = re.compile(r"\b(writer|author|novelist|poet|philosopher|historian|essayist|critic|playwright|journalist|scientist|theologian|mathematician|economist|sociologist)\b", re.I)
    for r in results:
        if keywords.search(r.get("description", "")):
            return r.get("id")
    return results[0].get("id") if results else None


def from_wikidata(*, name: Optional[str] = None, qid: Optional[str] = None) -> dict:
    """Fetch a Wikidata entity for a person and pull description + image."""
    if not qid and name:
        qid = _wikidata_search(name)
    if not qid:
        return {}

    url = f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
    data = cached_fetch("wikidata_entity", qid, lambda: _fetch_json(url), url=url)
    if not data:
        return {}

    entities = data.get("entities") or {}
    entity = entities.get(qid) or {}
    out: dict = {}

    desc = (entity.get("descriptions") or {}).get("en", {}).get("value")
    if desc and isinstance(desc, str) and desc.strip():
        out["bio"] = desc.strip()

    claims = entity.get("claims") or {}

    # P18 — image (Commons filename)
    p18 = claims.get("P18") or []
    for claim in p18:
        try:
            filename = claim["mainsnak"]["datavalue"]["value"]
        except (KeyError, TypeError):
            continue
        if filename:
            # Special:FilePath redirects to the actual Commons file URL
            out["photo_url"] = (
                f"https://commons.wikimedia.org/wiki/Special:FilePath/{quote(filename)}?width=400"
            )
            break

    # P569 / P570 — birth / death (date)
    def _year_from_claim(claim_list):
        for c in claim_list:
            try:
                t = c["mainsnak"]["datavalue"]["value"]["time"]
            except (KeyError, TypeError):
                continue
            m = re.match(r"^[+-]?(\d{1,4})", t)
            if m:
                return int(m.group(1))
        return None

    by = _year_from_claim(claims.get("P569") or [])
    if by is not None:
        out["birth_year"] = by
    dy = _year_from_claim(claims.get("P570") or [])
    if dy is not None:
        out["death_year"] = dy

    return out


# ---------------------------------------------------------------------------
# Name normalization — handle multi-author + cataloging artifacts
# ---------------------------------------------------------------------------

_AUTHOR_SEPARATORS = re.compile(r"\s*(?:&|,| and |/| with )\s*", re.I)
_PARENS = re.compile(r"\s*\([^)]*\)\s*")  # strip parenthesized cataloging tags


def candidate_names(name: str) -> list[str]:
    """Generate fall-back name variants for sources that fail on the original.

    Returns the original first, then progressively cleaner variants.
    Always includes the original even if cleaning produces something else.
    """
    seen = set()
    out = []
    for variant in (name, _PARENS.sub("", name).strip(), _AUTHOR_SEPARATORS.split(name)[0].strip()):
        v = variant.strip()
        if v and v not in seen:
            out.append(v)
            seen.add(v)
    return out
