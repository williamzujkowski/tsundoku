"""Tests for enrich-wikipedia-books `is_book` filtering.

Regression: the original heuristic accepted any extract that contained
"published" — which let the Wikipedia article for *MissionForce: CyberStorm*
(1996 video game) leak into Matthew Mather's 2013 novel of the same name.
The fix rejects on Wikipedia's `description` (or extract head) naming a
non-book medium, and requires an explicit literary marker.
"""
import importlib.util
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(__file__))

# enrich-wikipedia-books.py uses a hyphen, so import via spec.
SCRIPT = Path(__file__).parent / "enrich-wikipedia-books.py"
_spec = importlib.util.spec_from_file_location("enrich_wikipedia_books", SCRIPT)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


@pytest.fixture
def enricher(monkeypatch):
    """A WikipediaBookEnricher with `safe_request` stubbed to a fake."""
    from enrichment_base import EnrichmentScript  # noqa
    enricher = mod.WikipediaBookEnricher.__new__(mod.WikipediaBookEnricher)
    enricher._fake_response = None
    monkeypatch.setattr(enricher, "safe_request",
                        lambda url, **kw: enricher._fake_response)
    return enricher


def test_rejects_video_game_summary(enricher):
    """Wikipedia returns the 1996 game when we ask for "CyberStorm"."""
    enricher._fake_response = {
        "type": "standard",
        "title": "MissionForce: CyberStorm",
        "description": "1996 video game",
        "extract": (
            "MissionForce: CyberStorm is a turn-based strategy game "
            "developed by Dynamix and published in 1996 by Sierra On-Line. "
            "The game is set in the Metaltech universe..."
        ),
    }
    book = {"title": "CyberStorm", "author": "Matthew Mather"}
    assert enricher.search(book) is None


def test_rejects_film_summary(enricher):
    enricher._fake_response = {
        "type": "standard",
        "title": "The Shining (film)",
        "description": "1980 horror film",
        "extract": "The Shining is a 1980 psychological horror film "
                   "directed by Stanley Kubrick...",
    }
    book = {"title": "The Shining", "author": "Stephen King"}
    assert enricher.search(book) is None


def test_accepts_real_novel_summary(enricher):
    enricher._fake_response = {
        "type": "standard",
        "title": "Dune (novel)",
        "description": "1965 science fiction novel by Frank Herbert",
        "extract": "Dune is a 1965 epic science fiction novel by American "
                   "author Frank Herbert. It is the first installment of "
                   "the six-book Dune saga and is one of the best-selling "
                   "science fiction novels of all time.",
        "thumbnail": {"source": "https://upload.wikimedia.org/dune.jpg"},
    }
    book = {"title": "Dune", "author": "Frank Herbert"}
    out = enricher.search(book)
    assert out is not None
    assert "Frank Herbert" in out["description"] or "novel" in out["description"]


def test_accepts_via_author_last_name(enricher):
    """Even without the word 'novel', an extract that names the author
    by last name should pass."""
    enricher._fake_response = {
        "type": "standard",
        "title": "Cryptonomicon",
        "description": "1999 work by Neal Stephenson",
        "extract": "Cryptonomicon is the 1999 magnum opus from Stephenson, "
                   "weaving WW2 cryptography with present-day data havens. "
                   "Critics called it Stephenson's most ambitious effort.",
    }
    book = {"title": "Cryptonomicon", "author": "Neal Stephenson"}
    out = enricher.search(book)
    assert out is not None


def test_disambiguation_skipped(enricher):
    enricher._fake_response = {"type": "disambiguation",
                               "extract": "Foo may refer to:"}
    book = {"title": "Foo", "author": "Anonymous"}
    assert enricher.search(book) is None


def test_album_rejected(enricher):
    enricher._fake_response = {
        "type": "standard",
        "title": "Cryptonomicon (album)",
        "description": "studio album",
        "extract": "Cryptonomicon is a studio album by ...",
    }
    book = {"title": "Cryptonomicon", "author": "Neal Stephenson"}
    assert enricher.search(book) is None


def test_rejects_war_article_with_author_in_extract(enricher):
    """Regression: 'The Gallic War' returns the Wikipedia article about
    the 58–50 BC conflict, not the book. The extract trivially mentions
    'Caesar' (author last name) but the description is about the war,
    so the heuristic should reject."""
    enricher._fake_response = {
        "type": "standard",
        "title": "The Gallic War",
        "description": "58–50 BC conflict between Rome and Gallic tribes",
        "extract": ("The Gallic Wars were a series of military "
                    "campaigns waged by the Roman proconsul Julius "
                    "Caesar against several Gallic tribes."),
        "thumbnail": {"source": "https://upload/painting.jpg",
                      "width": 330, "height": 220},
    }
    book = {"title": "The Gallic War", "author": "Julius Caesar"}
    assert enricher.search(book) is None


def test_rejects_subject_illustration_thumbnail(enricher):
    """The article passes the is_book check but the lead image is a
    landscape painting/manuscript photo, not a cover. Description and
    extract are accepted; the thumbnail must still be rejected."""
    enricher._fake_response = {
        "type": "standard",
        "title": "Maxims of Ptahhotep",
        "description": "ancient Egyptian wisdom literature",
        "extract": ("The Maxims of Ptahhotep is a literary work of the "
                    "Ancient Egyptian wisdom genre, attributed to "
                    "Ptahhotep, vizier of Pharaoh Djedkare Isesi..."),
        "thumbnail": {"source": "https://upload/Papyrus_Prisse_187.jpg",
                      "width": 330, "height": 123},
    }
    book = {"title": "The Maxims of Ptahhotep", "author": "Ptahhotep"}
    out = enricher.search(book)
    assert out is not None
    assert "description" in out
    # Thumbnail rejected — aspect 2.68 is way past book-portrait range.
    assert "cover_url" not in out


def test_accepts_portrait_thumbnail(enricher):
    enricher._fake_response = {
        "type": "standard",
        "title": "Dune (novel)",
        "description": "1965 science fiction novel by Frank Herbert",
        "extract": "Dune is a 1965 epic science fiction novel by Herbert...",
        "thumbnail": {"source": "https://upload/Dune-Frank_Herbert_(1965)_First_edition.jpg",
                      "width": 200, "height": 304},  # aspect 0.66
    }
    book = {"title": "Dune", "author": "Frank Herbert"}
    out = enricher.search(book)
    assert out is not None
    assert out.get("cover_url") == \
        "https://upload/Dune-Frank_Herbert_(1965)_First_edition.jpg"
