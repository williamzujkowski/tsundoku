"""Tests for cache-photos.py — covers content-type → ext mapping, idempotency
on already-local URLs, JSON rewriting on success, no-modification on failure."""

import importlib.util
import json
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(__file__))

# Module name has a hyphen, so import via spec.
_spec = importlib.util.spec_from_file_location(
    "cache_photos", Path(__file__).parent / "cache-photos.py"
)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


class TestIsAlreadyLocal:
    def test_local_paths(self):
        assert mod.is_already_local("/tsundoku/cached/authors/plato.jpg")
        assert mod.is_already_local("/cached/authors/plato.jpg")

    def test_upstream_paths(self):
        assert not mod.is_already_local("https://upload.wikimedia.org/wiki/foo.jpg")
        assert not mod.is_already_local("https://covers.openlibrary.org/b/id/123-L.jpg")


class TestExtFromResponse:
    def test_jpeg(self):
        assert mod.ext_from_response("image/jpeg", "https://x/y.jpg") == "jpg"

    def test_jpeg_with_charset(self):
        assert mod.ext_from_response("image/jpeg; charset=binary", "https://x/y") == "jpg"

    def test_png(self):
        assert mod.ext_from_response("image/png", "https://x/y.png") == "png"

    def test_webp(self):
        assert mod.ext_from_response("image/webp", "https://x/y") == "webp"

    def test_unknown_type_falls_back_to_url_suffix(self):
        assert mod.ext_from_response("application/octet-stream", "https://x/y.png") == "png"

    def test_unknown_everything_defaults_jpg(self):
        assert mod.ext_from_response(None, "https://x/no-suffix") == "jpg"

    def test_jpeg_url_normalized_to_jpg(self):
        assert mod.ext_from_response(None, "https://x/y.jpeg") == "jpg"


class TestCacheOne:
    def test_skips_when_already_local(self, tmp_path, monkeypatch):
        out_dir = tmp_path / "authors"
        result = mod.cache_one(
            url="/tsundoku/cached/authors/plato.jpg",
            out_dir=out_dir,
            slug="plato",
            rate_limit_s=0,
        )
        assert result is None  # nothing to do

    def test_uses_existing_recent_file_without_redownload(self, tmp_path, monkeypatch):
        out_dir = tmp_path / "authors"
        out_dir.mkdir()
        # Existing recent file (mtime = now)
        (out_dir / "plato.png").write_bytes(b"fake png bytes")

        # If download() were called, it would fail noisily — make sure it isn't.
        def boom(url):
            raise AssertionError(f"download() should not be called; got {url}")

        monkeypatch.setattr(mod, "download", boom)
        result = mod.cache_one(
            url="https://example.com/plato.png",
            out_dir=out_dir,
            slug="plato",
            rate_limit_s=0,
        )
        assert result is not None
        local_url, ext = result
        assert ext == "png"
        assert local_url.endswith("/cached/authors/plato.png")

    def test_redownloads_if_existing_file_is_old(self, tmp_path, monkeypatch):
        out_dir = tmp_path / "authors"
        out_dir.mkdir()
        old_file = out_dir / "plato.jpg"
        old_file.write_bytes(b"old data")
        # Pretend it's 200 days old
        ancient = time.time() - 200 * 86400
        os.utime(old_file, (ancient, ancient))

        monkeypatch.setattr(mod, "download", lambda u: (b"fresh data", "jpg"))
        result = mod.cache_one(
            url="https://example.com/plato.jpg",
            out_dir=out_dir,
            slug="plato",
            rate_limit_s=0,
        )
        assert result is not None
        assert old_file.read_bytes() == b"fresh data"

    def test_returns_none_on_download_failure(self, tmp_path, monkeypatch):
        out_dir = tmp_path / "authors"
        monkeypatch.setattr(mod, "download", lambda u: None)
        result = mod.cache_one(
            url="https://example.com/dead.jpg",
            out_dir=out_dir,
            slug="dead",
            rate_limit_s=0,
        )
        assert result is None
        # No file was written
        assert not (out_dir / "dead.jpg").exists()

    def test_writes_atomically(self, tmp_path, monkeypatch):
        """Verifies the .tmp + rename pattern: success writes the final file."""
        out_dir = tmp_path / "authors"
        monkeypatch.setattr(mod, "download", lambda u: (b"image bytes", "jpg"))
        result = mod.cache_one(
            url="https://example.com/x.jpg",
            out_dir=out_dir,
            slug="x",
            rate_limit_s=0,
        )
        assert result is not None
        assert (out_dir / "x.jpg").read_bytes() == b"image bytes"
        # No leftover .tmp file
        leftovers = list(out_dir.glob("*.tmp"))
        assert leftovers == []


class TestProcessAuthors:
    def test_dead_url_does_not_modify_json(self, tmp_path, monkeypatch):
        authors = tmp_path / "authors"
        authors.mkdir()
        author_file = authors / "test.json"
        original = {
            "name": "Test",
            "slug": "test",
            "book_count": 1,
            "photo_url": "https://dead.example/x.jpg",
        }
        author_file.write_text(json.dumps(original))

        monkeypatch.setattr(mod, "AUTHORS_DIR", authors)
        monkeypatch.setattr(mod, "PUBLIC_CACHED", tmp_path / "public" / "cached")
        monkeypatch.setattr(mod, "download", lambda u: None)  # always fail

        counts = mod.process_authors(limit=0, dry_run=False, rate_limit_s=0)

        assert counts["failed"] == 1
        # JSON unchanged
        assert json.loads(author_file.read_text()) == original

    def test_successful_download_rewrites_json(self, tmp_path, monkeypatch):
        authors = tmp_path / "authors"
        authors.mkdir()
        author_file = authors / "plato.json"
        original = {
            "name": "Plato",
            "slug": "plato",
            "book_count": 21,
            "photo_url": "https://upload.wikimedia.org/plato.jpg",
            "bio": "philosopher",
        }
        author_file.write_text(json.dumps(original))

        monkeypatch.setattr(mod, "AUTHORS_DIR", authors)
        monkeypatch.setattr(mod, "PUBLIC_CACHED", tmp_path / "public" / "cached")
        monkeypatch.setattr(mod, "download", lambda u: (b"plato photo bytes", "jpg"))

        counts = mod.process_authors(limit=0, dry_run=False, rate_limit_s=0)
        assert counts["downloaded"] == 1
        assert counts["failed"] == 0

        result = json.loads(author_file.read_text())
        # Upstream URL preserved for attribution
        assert result["photo_url_source"] == "https://upload.wikimedia.org/plato.jpg"
        # photo_url rewritten to local
        assert result["photo_url"] == "/tsundoku/cached/authors/plato.jpg"
        assert "photo_cached_at" in result
        # Other fields untouched
        assert result["bio"] == "philosopher"
        assert result["book_count"] == 21

    def test_dry_run_does_not_modify_files(self, tmp_path, monkeypatch):
        authors = tmp_path / "authors"
        authors.mkdir()
        author_file = authors / "x.json"
        original = '{"name":"X","slug":"x","book_count":1,"photo_url":"https://example.com/x.jpg"}'
        author_file.write_text(original)

        monkeypatch.setattr(mod, "AUTHORS_DIR", authors)
        monkeypatch.setattr(mod, "PUBLIC_CACHED", tmp_path / "public" / "cached")
        monkeypatch.setattr(mod, "download", lambda u: (b"data", "jpg"))

        mod.process_authors(limit=0, dry_run=True, rate_limit_s=0)
        # JSON untouched
        assert author_file.read_text() == original


class TestProcessBooks:
    def test_caches_largest_url_and_rewrites_both_fields(self, tmp_path, monkeypatch):
        """When both cover_url and cover_url_large exist, we download once
        (the large one) and rewrite both fields to point at it."""
        books = tmp_path / "books"
        books.mkdir()
        book_file = books / "1984.json"
        original = {
            "title": "1984",
            "author": "Orwell",
            "category": "Literature",
            "priority": 2,
            "slug": "1984",
            "cover_url": "https://covers.openlibrary.org/b/id/1-M.jpg",
            "cover_url_large": "https://covers.openlibrary.org/b/id/1-L.jpg",
        }
        book_file.write_text(json.dumps(original))

        downloads = []

        def fake_download(url):
            downloads.append(url)
            return b"cover bytes", "jpg"

        monkeypatch.setattr(mod, "BOOKS_DIR", books)
        monkeypatch.setattr(mod, "PUBLIC_CACHED", tmp_path / "public" / "cached")
        monkeypatch.setattr(mod, "download", fake_download)

        mod.process_books(limit=0, dry_run=False, rate_limit_s=0)

        # Exactly one download — the large URL only
        assert len(downloads) == 1
        assert downloads[0].endswith("-L.jpg")

        result = json.loads(book_file.read_text())
        assert result["cover_url"] == "/tsundoku/cached/covers/1984.jpg"
        assert result["cover_url_large"] == "/tsundoku/cached/covers/1984.jpg"
        assert result["cover_url_source"].endswith("-M.jpg")
        assert result["cover_url_large_source"].endswith("-L.jpg")

    def test_idempotent_already_local(self, tmp_path, monkeypatch):
        """Re-running on a record whose cover_url is already local does nothing."""
        books = tmp_path / "books"
        books.mkdir()
        book_file = books / "x.json"
        original = {
            "title": "X",
            "author": "Y",
            "category": "Z",
            "priority": 3,
            "slug": "x",
            "cover_url": "/tsundoku/cached/covers/x.jpg",
        }
        book_file.write_text(json.dumps(original))

        monkeypatch.setattr(mod, "BOOKS_DIR", books)
        monkeypatch.setattr(mod, "PUBLIC_CACHED", tmp_path / "public" / "cached")
        # download() should not be called
        monkeypatch.setattr(mod, "download", lambda u: pytest.fail("unexpected download"))

        counts = mod.process_books(limit=0, dry_run=False, rate_limit_s=0)
        assert counts["cached_already"] == 1
        assert counts["downloaded"] == 0
