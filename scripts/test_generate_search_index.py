"""Tests for generate-search-index.py, including the companion
random-slugs.json emitted for RandomBook.svelte (#203)."""

import importlib.util
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

# Module name has a hyphen, so import via spec.
_spec = importlib.util.spec_from_file_location(
    "generate_search_index", Path(__file__).parent / "generate-search-index.py"
)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def _write_book(books_dir: Path, slug: str, title: str) -> None:
    (books_dir / f"{slug}.json").write_text(
        json.dumps(
            {
                "title": title,
                "author": "Some Author",
                "category": "Fiction",
                "slug": slug,
            }
        )
    )


def _write_author(authors_dir: Path, slug: str, name: str) -> None:
    (authors_dir / f"{slug}.json").write_text(
        json.dumps({"name": name, "slug": slug, "book_count": 1})
    )


def _run_with_fixtures(tmp_path, monkeypatch):
    books_dir = tmp_path / "books"
    authors_dir = tmp_path / "authors"
    books_dir.mkdir()
    authors_dir.mkdir()
    _write_book(books_dir, "dune", "Dune")
    _write_book(books_dir, "1984", "1984")
    _write_author(authors_dir, "frank-herbert", "Frank Herbert")

    search_out = tmp_path / "search-index.json"
    random_out = tmp_path / "random-slugs.json"

    monkeypatch.setattr(mod, "BOOKS_DIR", books_dir)
    monkeypatch.setattr(mod, "AUTHORS_DIR", authors_dir)
    monkeypatch.setattr(mod, "OUTPUT", search_out)
    monkeypatch.setattr(mod, "RANDOM_SLUGS_OUTPUT", random_out)

    mod.main()
    return search_out, random_out


class TestRandomSlugs:
    def test_emits_random_slugs_file(self, tmp_path, monkeypatch):
        _, random_out = _run_with_fixtures(tmp_path, monkeypatch)
        assert random_out.exists()

    def test_random_slugs_are_book_urls_only(self, tmp_path, monkeypatch):
        _, random_out = _run_with_fixtures(tmp_path, monkeypatch)
        slugs = json.loads(random_out.read_text())
        assert set(slugs) == {"books/dune/", "books/1984/"}
        # Authors must never appear in the random-book index.
        assert all(u.startswith("books/") for u in slugs)

    def test_random_slugs_is_plain_array_of_strings(self, tmp_path, monkeypatch):
        _, random_out = _run_with_fixtures(tmp_path, monkeypatch)
        slugs = json.loads(random_out.read_text())
        assert isinstance(slugs, list)
        assert all(isinstance(u, str) for u in slugs)

    def test_search_index_still_includes_authors(self, tmp_path, monkeypatch):
        search_out, _ = _run_with_fixtures(tmp_path, monkeypatch)
        items = json.loads(search_out.read_text())
        types = {i["y"] for i in items}
        assert "book" in types
        assert "author" in types

    def test_random_slugs_smaller_than_search_index(self, tmp_path, monkeypatch):
        search_out, random_out = _run_with_fixtures(tmp_path, monkeypatch)
        assert random_out.stat().st_size < search_out.stat().st_size
