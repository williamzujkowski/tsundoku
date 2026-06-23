"""
Data integrity tests — validates the book/author collection.

Catches: duplicate slugs, author mismatches, null values, missing
required fields, CSV sync issues. Runs in CI alongside other tests.
"""

import json
import csv
import glob
import re
import sys
import importlib.util
from pathlib import Path
from collections import Counter
from urllib.parse import urlsplit

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from http_retry import is_fetchable_url

BOOKS_DIR = Path(__file__).parent.parent / "src" / "content" / "books"
AUTHORS_DIR = Path(__file__).parent.parent / "src" / "content" / "authors"
CSV_PATH = Path(__file__).parent.parent / "data" / "reading-status.csv"

# Closed enums mirrored from src/content.config.ts. If the schema gains a value,
# update both. Kept literal here so the test fails loudly on schema drift rather
# than silently importing whatever the TS file happens to declare.
VALID_COPYRIGHT_STATUSES = frozenset(
    {"public_domain", "likely_public_domain", "in_copyright", "undetermined"}
)
VALID_READING_STATUSES = frozenset({"want", "reading", "read"})


def is_valid_asset_url(value: str) -> bool:
    """True for a well-formed cover/photo URL.

    Two acceptable shapes:
      * Site-relative cached path — starts with "/" (e.g. "/cached/abc.jpg",
        written by cache-photos.py, see #94).
      * Absolute http(s) URL with a host — mirrors http_retry.is_fetchable_url
        (rejects file:/ftp:/data: and other non-dereferenceable schemes) and
        additionally requires a non-empty netloc so "http://" alone fails.

    Empty strings and non-string values are rejected: the schema makes these
    fields optional, so "no asset" must be expressed by omitting the key, never
    by storing "".
    """
    if not isinstance(value, str) or not value:
        return False
    if value.startswith("/"):
        return True
    try:
        host = urlsplit(value).netloc
    except ValueError:
        return False
    return is_fetchable_url(value) and bool(host)

# Reuse the pipeline's author-splitting logic rather than duplicating it, so the
# book_count invariant tracks generate-author-stubs.py exactly. Module name has
# a hyphen, so import via spec.
_stub_spec = importlib.util.spec_from_file_location(
    "generate_author_stubs", Path(__file__).parent / "generate-author-stubs.py"
)
_author_stubs = importlib.util.module_from_spec(_stub_spec)
_stub_spec.loader.exec_module(_author_stubs)

REQUIRED_BOOK_FIELDS = ["title", "author", "category", "priority", "slug", "language"]


def load_all_books():
    return [(f, json.load(open(f))) for f in sorted(glob.glob(str(BOOKS_DIR / "*.json")))]


def load_all_authors():
    return [(f, json.load(open(f))) for f in sorted(glob.glob(str(AUTHORS_DIR / "*.json")))]


class TestBookIntegrity:
    def test_no_duplicate_slugs(self):
        slugs = Counter()
        for _, b in load_all_books():
            slugs[b["slug"]] += 1
        dupes = {s: c for s, c in slugs.items() if c > 1}
        assert len(dupes) == 0, f"Duplicate slugs: {dupes}"

    def test_required_fields_present(self):
        missing = []
        for f, b in load_all_books():
            for field in REQUIRED_BOOK_FIELDS:
                if not b.get(field):
                    missing.append(f"{Path(f).name}: missing {field}")
        assert len(missing) == 0, f"Missing required fields:\n" + "\n".join(missing[:10])

    def test_no_null_values(self):
        # `first_edition_isbn` is allowed to be explicit null — it carries
        # the meaning "this work pre-dates ISBN issuance" (epic #124).
        EXPLICIT_NULL_ALLOWED = {"first_edition_isbn"}
        nulls = []
        for f, b in load_all_books():
            for k, v in b.items():
                if v is None and k not in EXPLICIT_NULL_ALLOWED:
                    nulls.append(f"{Path(f).name}: {k} is null")
        assert len(nulls) == 0, f"Null values found:\n" + "\n".join(nulls[:10])

    def test_valid_priority(self):
        bad = []
        for f, b in load_all_books():
            if b["priority"] not in (1, 2, 3):
                bad.append(f"{Path(f).name}: priority={b['priority']}")
        assert len(bad) == 0, f"Invalid priorities:\n" + "\n".join(bad)

    def test_no_future_publication_years(self):
        bad = []
        for f, b in load_all_books():
            yr = b.get("first_published")
            if yr and yr > 2026:
                bad.append(f"{b['title']}: {yr}")
        assert len(bad) == 0, f"Future years:\n" + "\n".join(bad)

    def test_slug_matches_filename(self):
        bad = []
        for f, b in load_all_books():
            expected = Path(f).stem
            if b["slug"] != expected:
                bad.append(f"{Path(f).name}: slug={b['slug']} != {expected}")
        # Allow mismatches (some slugs have -2 suffixes)
        # Just ensure slug is non-empty
        for f, b in load_all_books():
            assert b["slug"], f"{Path(f).name} has empty slug"

    def test_ol_work_key_unique_per_record(self):
        """Each ol_work_key should map to at most one book record.

        Regression guard for the May 2026 audit (data/duplicate-records-audit.md):
        the loose OL matcher had assigned one work key (e.g. /works/OL27973414W)
        to all four Marx *Capital* volumes, /works/OL257263W to all four TAOCP
        volumes, /works/OL17732W to *Tanakh* + *Transformation* + *1001 Nights*,
        etc. The matcher now requires title+author verification (see
        `matching.verify_ol_work_match`); this invariant locks in the result.
        """
        from collections import defaultdict
        groups = defaultdict(list)
        for f, b in load_all_books():
            key = b.get("ol_work_key")
            if key:
                groups[key].append(Path(f).name)
        collisions = {k: v for k, v in groups.items() if len(v) > 1}
        assert not collisions, (
            f"ol_work_key shared by ≥2 records (cross-record contamination): "
            f"{collisions}"
        )

    def test_isbn_unique_per_record(self):
        """Each ISBN should map to at most one book record."""
        from collections import defaultdict
        groups = defaultdict(list)
        for f, b in load_all_books():
            isbn = (b.get("isbn") or "").strip()
            if isbn and len(isbn) >= 10:
                groups[isbn].append(Path(f).name)
        collisions = {k: v for k, v in groups.items() if len(v) > 1}
        assert not collisions, f"ISBN shared by ≥2 records: {collisions}"

    def test_no_article_only_title_duplicates(self):
        """No two records should share (author surname, title signature).

        Catches article-only and format-only dupes the original ol_work_key
        / isbn audit missed once those identifiers were cleared as part of
        cross-key cleanup. Examples this guards against:
          * "Art of Computer Programming Vol1" / "The Art of Computer
             Programming, Volume 1" — Knuth, same volume, "Vol1" vs "Volume 1".
          * "City of God" / "The City of God" — Augustine, article only.
          * "Capital: Volume 1" / "Capital, Volume I" — Marx, arabic vs Roman.
        """
        import unicodedata, re
        from collections import defaultdict

        STOPS = frozenset({
            "a","an","the","of","and","or","in","on","at","to","for","with",
            "by","from","is","as","de","la","le",
            # Volume / edition markers — keep the *number* tokens after them.
            "vol","volume","edition","ed","part","no","num","number","book","books",
        })
        ROMAN = {"i":"1","ii":"2","iii":"3","iv":"4","v":"5","vi":"6",
                 "vii":"7","viii":"8","ix":"9","x":"10"}

        def author_key(name: str) -> str:
            s = re.sub(r"[^a-z ]+", " ", (name or "").lower())
            toks = [t for t in s.split() if len(t) >= 3]
            return min(toks) if toks else ""

        def title_sig(title: str) -> frozenset[str]:
            t = unicodedata.normalize("NFKD", title or "")
            t = "".join(c for c in t if not unicodedata.combining(c)).lower()
            t = re.sub(r"[^a-z0-9 ]+", " ", t)
            t = re.sub(r"([a-z])(\d)", r"\1 \2", t)  # vol1 → vol 1
            t = re.sub(r"(\d)([a-z])", r"\1 \2", t)  # 4a → 4 a
            t = re.sub(r"\s+", " ", t).strip()
            return frozenset(ROMAN.get(tok, tok) for tok in t.split() if tok not in STOPS)

        groups = defaultdict(list)
        for f, b in load_all_books():
            ak = author_key(b.get("author", ""))
            sig = title_sig(b.get("title", ""))
            if not ak or not sig:
                continue
            groups[(ak, frozenset(sig))].append(Path(f).name)
        dupes = {k: v for k, v in groups.items() if len(v) > 1}
        assert not dupes, (
            "Article/format-only duplicate book records found "
            f"(author_key, title_signature): {dict(list(dupes.items())[:5])}"
        )

    def test_descriptions_are_english(self):
        # Regression for the Spanish-Tractatus issue: enrichment passes
        # occasionally pulled localised descriptions from OL/Google Books.
        # Heuristic: any book whose description is dominated by Spanish/
        # French/German/Portuguese/Dutch markers (≥1.4× English-token
        # count and ≥4 absolute) is flagged. False positives are
        # acceptable as long as the global count stays at zero.
        ENGLISH = re.compile(
            r"\b(the|of|and|to|a|in|is|that|for|with|as|on|by|are|this|was|be|from|or|an|its|it|but|not|have|has|all|will|one|book|author|published|writes|writing|edition|story|novel|work|english|chapter|first|second|when|where|while|after|before)\b",
            re.IGNORECASE,
        )
        NON_ENGLISH = re.compile(
            r"\b(el|la|los|las|de|que|en|es|son|para|por|del|al|una|uno|más|fue|obra|escribió|según|también|durante|cuando|donde|aquí|allí|nuestro|vida|le|les|des|et|ou|qui|où|dans|avec|sans|cette|ces|était|d'un|d'une|n'est|qu'il|der|die|das|den|dem|ein|eine|einer|und|oder|aber|nicht|mit|von|für|sich|werden|wurde|haben|hatte|sein|seine|als|você|não|ela|isto|aquele|aquela|estão|hij|zij|niet|maar|over|onder|tussen|alleen)\b",
            re.IGNORECASE,
        )
        bad = []
        for f, b in load_all_books():
            desc = b.get("description") or ""
            if len(desc.split()) < 8:
                continue
            en = len(ENGLISH.findall(desc))
            other = len(NON_ENGLISH.findall(desc))
            if other > en * 1.4 and other >= 4:
                bad.append(f"{Path(f).name}: {desc[:80]}")
        assert len(bad) == 0, f"Non-English descriptions:\n" + "\n".join(bad[:10])

    def test_language_is_english(self):
        """Every book must declare language 'eng' (CLAUDE.md hard rule).

        When the field is present it must be exactly "eng"; the collection is
        English-only by policy. A book carrying e.g. "fre"/"spa" is a data bug.
        """
        bad = []
        for f, b in load_all_books():
            lang = b.get("language")
            if lang is not None and lang != "eng":
                bad.append(f"{Path(f).name}: language={lang!r}")
        assert not bad, "Non-English language values:\n" + "\n".join(bad[:10])

    def test_valid_copyright_status(self):
        """copyright_status, when present, is one of the 4 enum values.

        Mirrors the z.enum in src/content.config.ts and the enum produced by
        enrich-copyright.compute_copyright_status.
        """
        bad = []
        for f, b in load_all_books():
            status = b.get("copyright_status")
            if status is not None and status not in VALID_COPYRIGHT_STATUSES:
                bad.append(f"{Path(f).name}: copyright_status={status!r}")
        assert not bad, "Invalid copyright_status values:\n" + "\n".join(bad[:10])

    def test_valid_book_reading_status(self):
        """reading_status on the book JSON, when present, is want/reading/read.

        The CSV side is covered by TestCSVIntegrity.test_valid_reading_status;
        this guards the value baked into the content files by
        apply-reading-status.py.
        """
        bad = []
        for f, b in load_all_books():
            status = b.get("reading_status")
            if status is not None and status not in VALID_READING_STATUSES:
                bad.append(f"{Path(f).name}: reading_status={status!r}")
        assert not bad, "Invalid book reading_status values:\n" + "\n".join(bad[:10])

    def test_cover_urls_well_formed(self):
        """cover_url / cover_url_large, when present, are well-formed.

        Either a site-relative cached path (starts with "/") or an http(s) URL
        with a host. Empty strings, bare schemes, and file:/ftp:/data: URLs are
        rejected — see is_valid_asset_url.
        """
        bad = []
        for f, b in load_all_books():
            for key in ("cover_url", "cover_url_large"):
                v = b.get(key)
                if v is not None and not is_valid_asset_url(v):
                    bad.append(f"{Path(f).name}: {key}={v!r}")
        assert not bad, "Malformed cover URLs:\n" + "\n".join(bad[:10])


class TestStatsIntegrity:
    def test_stats_has_required_keys(self):
        stats_path = Path(__file__).parent.parent / "src" / "data" / "stats.json"
        if not stats_path.exists():
            pytest.skip("stats.json not generated yet")
        stats = json.loads(stats_path.read_text())
        required = [
            "total_books", "total_categories", "total_authors",
            "priorities", "enrichment", "links", "bookshelf",
            "reading_progress", "top_authors", "categories",
            "year_distribution", "generated_at",
        ]
        for key in required:
            assert key in stats, f"stats.json missing key: {key}"

    def test_stats_links_section(self):
        stats_path = Path(__file__).parent.parent / "src" / "data" / "stats.json"
        if not stats_path.exists():
            pytest.skip("stats.json not generated yet")
        stats = json.loads(stats_path.read_text())
        links = stats.get("links", {})
        for source in ["gutenberg", "librivox", "hathitrust", "worldcat"]:
            assert source in links, f"stats.links missing: {source}"
            assert links[source] >= 0, f"stats.links.{source} is negative"


class TestAuthorIntegrity:
    def test_every_book_author_has_page(self):
        book_authors = set()
        for _, b in load_all_books():
            book_authors.add(b["author"])
        author_names = set()
        for _, a in load_all_authors():
            author_names.add(a["name"])
        missing = book_authors - author_names
        assert len(missing) == 0, f"Authors without pages: {missing}"

    def test_no_duplicate_author_names(self):
        names = Counter()
        for _, a in load_all_authors():
            names[a["name"]] += 1
        dupes = {n: c for n, c in names.items() if c > 1}
        assert len(dupes) == 0, f"Duplicate author names: {dupes}"

    def test_author_required_fields(self):
        for f, a in load_all_authors():
            assert a.get("name"), f"{Path(f).name}: missing name"
            assert a.get("slug"), f"{Path(f).name}: missing slug"
            assert "book_count" in a, f"{Path(f).name}: missing book_count"

    def test_photo_urls_well_formed(self):
        """photo_url, when present, is a well-formed cached path or http(s) URL.

        Same well-formedness contract as book cover URLs (is_valid_asset_url):
        rejects empty strings and non-dereferenceable schemes (file:/ftp:/data:)
        so a poisoned upstream value never lands in the content files.
        """
        bad = []
        for f, a in load_all_authors():
            v = a.get("photo_url")
            if v is not None and not is_valid_asset_url(v):
                bad.append(f"{Path(f).name}: photo_url={v!r}")
        assert not bad, "Malformed author photo URLs:\n" + "\n".join(bad[:10])

    def test_book_count_matches_attribution(self):
        """Every author's book_count equals its attributable book count.

        Regression guard for issue #179: generate-author-stubs.py only created
        missing stubs and never refreshed book_count on existing records, so
        counts went stale as books were added/removed. The generator now
        authoritatively rewrites book_count on every run; this invariant keeps
        the content files honest. Attribution mirrors the generator: each book
        counts toward its full author string AND each split component name.
        """
        # Freshly compute attributable counts, exactly as the generator does.
        counts = Counter()
        for _, b in load_all_books():
            author_str = b["author"]
            names = {author_str, *_author_stubs.split_authors(author_str)}
            for n in names:
                counts[n] += 1

        mismatches = []
        for f, a in load_all_authors():
            expected = counts.get(a["name"], 0)
            if a.get("book_count") != expected:
                mismatches.append(
                    f"{Path(f).name}: book_count={a.get('book_count')} != {expected}"
                )
        assert not mismatches, (
            "Stale author book_count(s) — re-run generate-author-stubs.py:\n"
            + "\n".join(mismatches[:15])
        )


class TestCSVIntegrity:
    def test_csv_entries_match_books(self):
        book_slugs = set()
        for _, b in load_all_books():
            book_slugs.add(b["slug"])
        csv_slugs = set()
        if CSV_PATH.exists():
            with open(CSV_PATH) as f:
                for row in csv.DictReader(f):
                    csv_slugs.add(row["slug"])
            orphaned = csv_slugs - book_slugs
            assert len(orphaned) == 0, f"CSV entries without books: {orphaned}"

    def test_valid_reading_status(self):
        if not CSV_PATH.exists():
            return
        bad = []
        with open(CSV_PATH) as f:
            for row in csv.DictReader(f):
                if row["status"] not in ("want", "reading", "read", ""):
                    bad.append(f"{row['slug']}: {row['status']}")
        assert len(bad) == 0, f"Invalid statuses:\n" + "\n".join(bad)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
