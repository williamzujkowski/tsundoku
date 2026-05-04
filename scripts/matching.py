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


def authors_match(query_author: str, candidate_authors) -> bool:
    """True if any candidate author shares a last name with the query author.

    `candidate_authors` may be a list (OL `author_name`) or a string. Returns
    False on empty input — callers should reject such matches outright.
    """
    if not query_author:
        return False
    if isinstance(candidate_authors, str):
        candidate_authors = [candidate_authors]
    if not candidate_authors:
        return False
    q_last = author_last_name(query_author)
    if not q_last:
        return False
    for cand in candidate_authors:
        if not cand:
            continue
        if author_last_name(cand) == q_last:
            return True
        # token-level last-name match for joint authors like "Cormen et al."
        cand_tokens = {t.lower().rstrip(".,") for t in cand.split() if t}
        if q_last in cand_tokens:
            return True
    return False


def verify_ol_work_match(
    *,
    book_title: str,
    book_author: str,
    work_title: str,
    work_authors,
    title_threshold: float = 0.5,
) -> tuple[bool, str]:
    """Decide whether an OL work record really matches the local book.

    Returns (ok, reason). When `ok` is False, callers MUST NOT write the
    work's `key` (ol_work_key) onto the local record. Loose matches are how
    `OL27973414W` ended up shared across all four Marx *Capital* volumes —
    title-only similarity isn't enough; author surname must also align.

    `title_threshold` defaults to 0.5 (token Jaccard from `title_similarity`),
    which still allows article/punctuation drift (e.g. "Discourse on Method"
    ↔ "Discourse on the Method") while rejecting different-volume cases
    ("Capital, Volume II" ↔ "Capital, Volume I" → similarity 0.5 but author
    check still passes for both Marx — title rejection has to catch this via
    explicit volume-token comparison upstream).
    """
    if not work_title:
        return False, "empty work title"
    if not authors_match(book_author, work_authors):
        return False, f"author mismatch: book={book_author!r} work={work_authors!r}"
    sim = title_similarity(strip_article(book_title), strip_article(work_title))
    if not (book_title.lower() in work_title.lower()
            or work_title.lower() in book_title.lower()
            or sim >= title_threshold):
        return False, f"title mismatch (sim={sim:.2f}): book={book_title!r} work={work_title!r}"
    return True, "ok"
