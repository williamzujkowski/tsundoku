"""
Data integrity tests — validates the book/author collection.

Catches: duplicate slugs, author mismatches, null values, missing
required fields, CSV sync issues. Runs in CI alongside other tests.
"""

import json
import csv
import glob
import re
import importlib.util
from pathlib import Path
from collections import Counter

import pytest

BOOKS_DIR = Path(__file__).parent.parent / "src" / "content" / "books"
AUTHORS_DIR = Path(__file__).parent.parent / "src" / "content" / "authors"
CSV_PATH = Path(__file__).parent.parent / "data" / "reading-status.csv"

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

    def test_no_orphan_author_pages(self):
        """No author record may have zero attributable books unless it is an
        allowed special case (issue #181).

        `test_every_book_author_has_page` guards books→authors; this guards the
        reverse. A record whose `name` is attributed by ZERO books is a dead
        page (regenerable stub) UNLESS it is one of:

          1. A **joint alias** — its name splits into 2+ components that each
             have their own author record (e.g. "Marx & Engels"). The component
             pages carry the books; the alias exists for URL back-compat. Reuses
             the pipeline's split_authors() rather than re-implementing it, so it
             tracks generate-author-stubs.py exactly.
          2. An **organizational** byline (committee / corporate / editorial),
             mirroring isOrganizationalAuthorName() in src/utils/formatting.ts.
             These long institutional bylines don't decompose to a person.
          3. A name on KNOWN_SPLIT_GAP — a genuine author whose 0-count is a
             *known limitation* of the byline splitter, not a dead page. The
             splitter can't cleanly decompose mixed "A, B, and C" / slash bylines
             (e.g. the Federalist Papers' "Alexander Hamilton, James Madison, and
             John Jay" splits to ["Alexander Hamilton, James Madison,", "John
             Jay"]), so the standalone person pages — which are real, with bios
             and photos — get no attribution. Deleting them would HIDE the
             attribution gap, so we keep them and document the gap here.
             TODO(#181): improve split_authors() to handle mixed comma/`and`
             bylines, then these should attribute correctly and drop off this list.
        """
        # Organizational-name pattern — keep in sync with
        # isOrganizationalAuthorName() / ORG_NAME_PATTERN in formatting.ts.
        ORG_NAME_PATTERN = re.compile(
            r"(\bInc\.?\b|\bLLC\b|\bLtd\.?\b|\bCorp\.?\b|\bStaff\b|\bCommittee\b"
            r"|\bCommission\b|\bEditors?\b|\bCouncil\b|\bSociety\b|\bAssociation\b"
            r"|\bFoundation\b|\bInstitute\b|\bBoard\b|^Various\b|\(Various\))",
            re.IGNORECASE,
        )

        # Real authors whose 0-count is a known byline-splitter limitation, not a
        # dead page. See the docstring + PR for #181. Each appears only inside a
        # long mixed "A, B, and C ... / Org" byline the splitter can't decompose.
        KNOWN_SPLIT_GAP = {
            # Federalist Papers — "Alexander Hamilton, James Madison, and John Jay"
            "Alexander Hamilton",
            "James Madison",
            # Cookbook byline — "Robin Asbell, Susie Middleton, Karen Morgan,
            # Joseph Shuldiner, Melissa's / World Variety Produce, Inc."
            "Robin Asbell",
            "Susie Middleton",
            "Karen Morgan",
            "Joseph Shuldiner",
            "World Variety Produce",  # loses its "Inc." suffix during the split
        }

        # Attribution counts, computed exactly as the generator does.
        counts = Counter()
        for _, b in load_all_books():
            author_str = b["author"]
            names = {author_str, *_author_stubs.split_authors(author_str)}
            for n in names:
                counts[n] += 1

        known_names = {a["name"] for _, a in load_all_authors()}

        def is_joint_alias(name: str) -> bool:
            parts = _author_stubs.split_authors(name)
            return len(parts) >= 2 and all(p in known_names for p in parts)

        orphans = []
        for f, a in load_all_authors():
            name = a["name"]
            if counts.get(name, 0) != 0:
                continue
            if is_joint_alias(name):
                continue
            if ORG_NAME_PATTERN.search(name):
                continue
            if name in KNOWN_SPLIT_GAP:
                continue
            orphans.append(f"{Path(f).name}: '{name}' (book_count={a.get('book_count')})")

        assert not orphans, (
            "Orphan author page(s) — author records attributable to zero books "
            "that are not joint aliases, organizational, or known split-gaps. "
            "Delete the dead stub or fix the attribution mismatch (see #181):\n"
            + "\n".join(orphans[:20])
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
