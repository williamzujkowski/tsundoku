"""
Shared title/author matching utilities for enrichment scripts.

All enrichment scripts require both title AND author match to prevent
false positives. This module provides the canonical matching logic.
"""


def title_similarity(a: str, b: str) -> float:
    """Word overlap ratio between two titles.

    Returns a float between 0.0 and 1.0 representing the fraction
    of words shared between the two titles.
    """
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    overlap = words_a & words_b
    return len(overlap) / max(len(words_a), len(words_b))


def strip_article(title: str) -> str:
    """Strip leading English articles (A, An, The) from a title."""
    for article in ("A ", "An ", "The "):
        if title.startswith(article):
            return title[len(article):]
    return title


def author_last_name(author: str) -> str:
    """Extract the last word of an author name for fuzzy matching."""
    parts = author.strip().split()
    return parts[-1].lower() if parts else ""


def titles_match(query_title: str, result_title: str, threshold: float = 0.6) -> bool:
    """Check if two titles match via containment or word overlap.

    Returns True if either title contains the other, or if the
    word overlap ratio exceeds the given threshold.
    """
    a = query_title.lower()
    b = result_title.lower()
    return a in b or b in a or title_similarity(a, b) > threshold
