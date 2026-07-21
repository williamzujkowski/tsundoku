"""Tests for the build-time /cached/ image-existence guard — see #234
(production 404 on /authors/william-shakespeare/: JSON claimed a local
cached path that was never actually downloaded onto the CI runner)."""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from image_guard import resolve_image_url


@pytest.fixture
def public_dir(tmp_path: Path) -> Path:
    (tmp_path / "cached" / "authors").mkdir(parents=True)
    (tmp_path / "cached" / "covers").mkdir(parents=True)
    return tmp_path


class TestNonLocalUrls:
    def test_none_returns_none(self, public_dir):
        assert resolve_image_url(None, public_dir=public_dir) is None

    def test_empty_string_returns_none(self, public_dir):
        assert resolve_image_url("", public_dir=public_dir) is None

    def test_remote_url_passes_through_unchanged(self, public_dir):
        url = "https://covers.openlibrary.org/b/id/8541860-L.jpg"
        assert resolve_image_url(url, public_dir=public_dir) == url

    def test_remote_url_passes_through_even_with_a_source(self, public_dir):
        # source_url only matters for local paths; a remote url is never
        # replaced by its own "source" (there isn't one).
        url = "https://covers.openlibrary.org/b/id/8541860-L.jpg"
        assert resolve_image_url(url, "https://example.com/other.jpg", public_dir=public_dir) == url


class TestLocalUrlFileExists:
    def test_tsundoku_base_prefixed_path_when_file_present(self, public_dir):
        (public_dir / "cached" / "authors" / "william-shakespeare.jpg").write_bytes(b"x")
        url = "/tsundoku/cached/authors/william-shakespeare.jpg"
        assert resolve_image_url(url, public_dir=public_dir) == url

    def test_legacy_unprefixed_cached_path_when_file_present(self, public_dir):
        (public_dir / "cached" / "covers" / "dune.jpg").write_bytes(b"x")
        url = "/cached/covers/dune.jpg"
        assert resolve_image_url(url, public_dir=public_dir) == url

    def test_nested_slug_with_dots_resolves_correctly(self, public_dir):
        (public_dir / "cached" / "covers" / "1984.jpg").write_bytes(b"x")
        url = "/tsundoku/cached/covers/1984.jpg"
        assert resolve_image_url(url, public_dir=public_dir) == url


class TestLocalUrlFileMissing:
    def test_falls_back_to_source_url_when_file_missing(self, public_dir):
        url = "/tsundoku/cached/authors/william-shakespeare.jpg"
        source = "https://upload.wikimedia.org/wikipedia/commons/thumb/2/21/William_Shakespeare.jpg"
        assert resolve_image_url(url, source, public_dir=public_dir) == source

    def test_returns_none_when_file_missing_and_no_source(self, public_dir):
        url = "/tsundoku/cached/authors/ghost.jpg"
        assert resolve_image_url(url, None, public_dir=public_dir) is None

    def test_returns_none_when_source_is_empty_string(self, public_dir):
        url = "/tsundoku/cached/authors/ghost.jpg"
        assert resolve_image_url(url, "", public_dir=public_dir) is None

    def test_never_raises_for_a_missing_cached_subdirectory(self, tmp_path):
        # public_dir with no "cached/" dir at all yet (fresh checkout,
        # cache-photos.py never ran) — must not raise.
        url = "/tsundoku/cached/authors/ghost.jpg"
        assert resolve_image_url(url, "https://example.com/x.jpg", public_dir=tmp_path) == "https://example.com/x.jpg"


class TestRealWorldRegression:
    def test_william_shakespeare_incident(self, public_dir):
        """The exact production incident: JSON says local, file is
        missing from this build's public/cached/, a source URL is on
        record — the guard must recover it rather than emit the 404."""
        doc = {
            "photo_url": "/tsundoku/cached/authors/william-shakespeare.jpg",
            "photo_url_source": (
                "https://upload.wikimedia.org/wikipedia/commons/thumb/2/21/"
                "William_Shakespeare_by_John_Taylor%2C_edited.jpg/400px-"
                "William_Shakespeare_by_John_Taylor%2C_edited.jpg"
            ),
        }
        resolved = resolve_image_url(doc["photo_url"], doc["photo_url_source"], public_dir=public_dir)
        assert resolved == doc["photo_url_source"]
        assert not resolved.startswith("/tsundoku/cached/")
