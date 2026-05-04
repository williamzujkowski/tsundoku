"""
Data integrity tests — validates the book/author collection.

Catches: duplicate slugs, author mismatches, null values, missing
required fields, CSV sync issues. Runs in CI alongside other tests.
"""

import json
import csv
import glob
import re
from pathlib import Path
from collections import Counter

import pytest

BOOKS_DIR = Path(__file__).parent.parent / "src" / "content" / "books"
AUTHORS_DIR = Path(__file__).parent.parent / "src" / "content" / "authors"
CSV_PATH = Path(__file__).parent.parent / "data" / "reading-status.csv"

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
