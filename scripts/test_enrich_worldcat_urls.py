import importlib.util
from pathlib import Path

# Dynamic import since the filename has dashes
spec = importlib.util.spec_from_file_location(
    "enrich_worldcat_urls", Path(__file__).parent / "enrich-worldcat-urls.py"
)
enrich_worldcat_urls = importlib.util.module_from_spec(spec)
spec.loader.exec_module(enrich_worldcat_urls)
build_worldcat_url = enrich_worldcat_urls.build_worldcat_url


def test_preserves_existing_worldcat_url():
    data = {
        "title": "Existing Book",
        "author": "Author",
        "worldcat_url": "https://www.worldcat.org/oclc/123456",
    }
    assert build_worldcat_url(data) == "https://www.worldcat.org/oclc/123456"


def test_uses_isbn_when_available():
    data = {
        "title": "Book With ISBN",
        "author": "Author",
        "isbn": "9780140449136",
    }
    assert build_worldcat_url(data) == "https://www.worldcat.org/isbn/9780140449136"


def test_falls_back_to_title_author_search():
    data = {
        "title": "Epic of Gilgamesh",
        "author": "Anonymous",
    }
    assert (
        build_worldcat_url(data)
        == "https://www.worldcat.org/search?q=Epic%20of%20Gilgamesh%20Anonymous"
    )


def test_handles_empty_fields():
    assert build_worldcat_url({}) is None
