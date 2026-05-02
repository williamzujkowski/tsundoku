"""Parser for Open Library edition `publish_date` strings.

OL date strings are messy. Real samples we'd encounter:

  "1719"                  → (1719, certain)
  "January 1719"          → (1719, certain)
  "1719, c1700"           → (1700, certain) — copyright date
  "1719?"                 → (1719, circa)
  "[1719]"                → (1719, certain — bracket means inferred but solid)
  "[1719?]"               → (1719, circa)
  "ca. 1850" / "c. 1850"  → (1850, circa)
  "circa 1850"            → (1850, circa)
  "19--" / "19uu"         → (1900, circa) — unknown decade in 20th century
  "20th century"          → (1900, circa)
  "n.d." / "no date"      → (None, circa)
  "1812-1813"             → (1812, certain) — range
  "1812 (rev. ed. 1815)"  → (1812, certain)
  "1812 reprint"          → (1812, certain)
  ""                      → (None, _)
  None                    → (None, _)
  "Unknown"               → (None, _)
  "BCE 100" / "100 BC"    → (-100, certain)
  "MDCCXIX"               → (1719, certain) — Roman numerals (rare)

Usage:
    from edition_date import parse_publish_date
    year, circa = parse_publish_date("ca. 1850")
    # → (1850, True)
"""

import re
from typing import Optional


# The pieces — each is tried in order against the cleaned input.
_BC_RE = re.compile(r"\b(\d{1,4})\s*(?:bc|bce|b\.c\.|b\.c\.e\.)\b", re.IGNORECASE)
_BC_PREFIX_RE = re.compile(r"\b(?:bc|bce)\s*(\d{1,4})\b", re.IGNORECASE)
_FOUR_DIGIT_RE = re.compile(r"\b(\d{4})\b")
_DECADE_APPROX_RE = re.compile(r"\b(\d{2})(?:--|uu|XX|\?\?)", re.IGNORECASE)
_CENTURY_RE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)\s*century\b", re.IGNORECASE)
_CIRCA_TOKENS = re.compile(r"\b(?:c\.?|ca\.?|circa|approximately|approx\.?|prob\.?|probable|maybe)\b", re.IGNORECASE)

# Roman numerals (rare — used for some old editions)
_ROMAN_VALUES = {
    "M": 1000, "CM": 900, "D": 500, "CD": 400,
    "C": 100, "XC": 90, "L": 50, "XL": 40,
    "X": 10, "IX": 9, "V": 5, "IV": 4, "I": 1,
}
_ROMAN_RE = re.compile(r"\b(?=[MDCLXVI])(M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3}))\b")


def _roman_to_int(s: str) -> Optional[int]:
    """Convert a roman numeral string to an int, or None if invalid."""
    if not s:
        return None
    s = s.upper()
    total = 0
    i = 0
    while i < len(s):
        if i + 1 < len(s) and s[i:i + 2] in _ROMAN_VALUES:
            total += _ROMAN_VALUES[s[i:i + 2]]
            i += 2
        elif s[i] in _ROMAN_VALUES:
            total += _ROMAN_VALUES[s[i]]
            i += 1
        else:
            return None
    return total if total > 0 else None


def parse_publish_date(s: Optional[str]) -> tuple[Optional[int], bool]:
    """Parse an OL `publish_date` string into (year, circa).

    Returns:
        (year, circa) where year is signed int (negative for BCE), or
        (None, circa) when no year can be extracted.
        `circa` is True when the parser is uncertain (e.g. "ca. 1850",
        a question mark, century-only, or a Roman numeral).
    """
    if not s or not s.strip():
        return (None, False)
    text = s.strip()
    if text.lower() in ("unknown", "n.d.", "no date", "undated"):
        return (None, True)

    # Detect circa qualifiers — these mark the year as uncertain regardless of source.
    circa = bool(_CIRCA_TOKENS.search(text)) or "?" in text or "[" in text and "]" in text and "?" in text

    # BCE — try suffix and prefix forms
    m = _BC_RE.search(text) or _BC_PREFIX_RE.search(text)
    if m:
        return (-int(m.group(1)), circa)

    # Standard 4-digit year — most common case
    m = _FOUR_DIGIT_RE.search(text)
    if m:
        return (int(m.group(1)), circa)

    # Decade approximate (19-- means 1900s sometime)
    m = _DECADE_APPROX_RE.search(text)
    if m:
        return (int(m.group(1)) * 100, True)

    # Century only — "19th century" → 1800s
    m = _CENTURY_RE.search(text)
    if m:
        century = int(m.group(1))
        return ((century - 1) * 100, True)

    # Last resort: Roman numeral (very rare)
    m = _ROMAN_RE.search(text)
    if m and m.group(1):
        n = _roman_to_int(m.group(1))
        if n and 100 <= n <= 2100:
            return (n, circa)

    return (None, True)


def earliest_year(dates: list[Optional[str]]) -> tuple[Optional[int], bool]:
    """Given a list of OL date strings, return (year, circa) of the earliest
    parseable one. If all dates are circa, the result is circa."""
    parsed = [parse_publish_date(d) for d in dates]
    parsed = [(y, c) for y, c in parsed if y is not None]
    if not parsed:
        return (None, False)
    parsed.sort(key=lambda x: x[0])
    return parsed[0]
