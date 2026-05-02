#!/usr/bin/env python3
"""Convert a Natural Earth 110m TopoJSON to a static SVG world map.

Output: src/data/world-map.svg with one <path id="XX"> per country, where
XX is the ISO 3166-1 alpha-2 code. The Astro stats page reads this SVG
inline and applies a CSS data-attribute fill driven by the per-country
book count.

Run once when the world atlas changes (it changes ~never). The output
SVG is small (~110KB), checked into git, no Node dependency at build
time.

Source data: https://unpkg.com/world-atlas@2/countries-110m.json
That file uses ISO 3166-1 numeric codes; we map them to alpha-2 below.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path


SOURCE_URL = "https://unpkg.com/world-atlas@2/countries-110m.json"
OUT_PATH = Path(__file__).parent.parent / "src" / "data" / "world-map.svg"

# Map width/height in SVG units. Equirectangular projection (linear
# longitude/latitude). 360x180 viewBox keeps math trivial.
MAP_W = 800
MAP_H = 400


# ISO 3166-1 numeric → alpha-2. Subset; we add codes only for countries
# that show up in our nationality_distribution. Unmapped country features
# are emitted with id="XX" (placeholder) so the path still renders but
# isn't selectable for fill.
NUMERIC_TO_ALPHA2 = {
    "004": "AF", "008": "AL", "012": "DZ", "020": "AD", "024": "AO",
    "028": "AG", "031": "AZ", "032": "AR", "036": "AU", "040": "AT",
    "044": "BS", "048": "BH", "050": "BD", "051": "AM", "052": "BB",
    "056": "BE", "060": "BM", "064": "BT", "068": "BO", "070": "BA",
    "072": "BW", "076": "BR", "084": "BZ", "090": "SB", "096": "BN",
    "100": "BG", "104": "MM", "108": "BI", "112": "BY", "116": "KH",
    "120": "CM", "124": "CA", "132": "CV", "140": "CF", "144": "LK",
    "148": "TD", "152": "CL", "156": "CN", "158": "TW", "170": "CO",
    "174": "KM", "178": "CG", "180": "CD", "188": "CR", "191": "HR",
    "192": "CU", "196": "CY", "203": "CZ", "204": "BJ", "208": "DK",
    "212": "DM", "214": "DO", "218": "EC", "222": "SV", "226": "GQ",
    "231": "ET", "232": "ER", "233": "EE", "242": "FJ", "246": "FI",
    "250": "FR", "254": "GF", "258": "PF", "260": "TF", "262": "DJ",
    "266": "GA", "268": "GE", "270": "GM", "275": "PS", "276": "DE",
    "288": "GH", "300": "GR", "304": "GL", "308": "GD", "320": "GT",
    "324": "GN", "328": "GY", "332": "HT", "340": "HN", "348": "HU",
    "352": "IS", "356": "IN", "360": "ID", "364": "IR", "368": "IQ",
    "372": "IE", "376": "IL", "380": "IT", "384": "CI", "388": "JM",
    "392": "JP", "398": "KZ", "400": "JO", "404": "KE", "408": "KP",
    "410": "KR", "414": "KW", "417": "KG", "418": "LA", "422": "LB",
    "426": "LS", "428": "LV", "430": "LR", "434": "LY", "438": "LI",
    "440": "LT", "442": "LU", "450": "MG", "454": "MW", "458": "MY",
    "466": "ML", "470": "MT", "478": "MR", "480": "MU", "484": "MX",
    "496": "MN", "498": "MD", "499": "ME", "504": "MA", "508": "MZ",
    "512": "OM", "516": "NA", "524": "NP", "528": "NL", "540": "NC",
    "548": "VU", "554": "NZ", "558": "NI", "562": "NE", "566": "NG",
    "578": "NO", "586": "PK", "591": "PA", "598": "PG", "600": "PY",
    "604": "PE", "608": "PH", "616": "PL", "620": "PT", "624": "GW",
    "626": "TL", "630": "PR", "634": "QA", "642": "RO", "643": "RU",
    "646": "RW", "682": "SA", "686": "SN", "688": "RS", "690": "SC",
    "694": "SL", "702": "SG", "703": "SK", "704": "VN", "705": "SI",
    "706": "SO", "710": "ZA", "716": "ZW", "724": "ES", "728": "SS",
    "729": "SD", "740": "SR", "748": "SZ", "752": "SE", "756": "CH",
    "760": "SY", "762": "TJ", "764": "TH", "768": "TG", "776": "TO",
    "780": "TT", "784": "AE", "788": "TN", "792": "TR", "795": "TM",
    "798": "TV", "800": "UG", "804": "UA", "807": "MK", "818": "EG",
    "826": "GB", "834": "TZ", "840": "US", "850": "VI", "854": "BF",
    "858": "UY", "860": "UZ", "862": "VE", "882": "WS", "887": "YE",
    "894": "ZM",
}


def fetch_topo() -> dict:
    print(f"Fetching {SOURCE_URL}...")
    req = urllib.request.Request(
        SOURCE_URL,
        headers={"User-Agent": "tsundoku-mapbuild/1.0"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def decode_arc(arc: list[list[int]]) -> list[tuple[int, int]]:
    """Cumulative-delta-decoded arc (TopoJSON quantized format)."""
    x = 0
    y = 0
    coords: list[tuple[int, int]] = []
    for dx, dy in arc:
        x += dx
        y += dy
        coords.append((x, y))
    return coords


def project(x_q: int, y_q: int, transform: dict) -> tuple[float, float]:
    """De-quantize and equirectangular-project to SVG coordinates."""
    sx, sy = transform["scale"]
    tx, ty = transform["translate"]
    lon = x_q * sx + tx
    lat = y_q * sy + ty
    # Equirectangular: lon → x, lat → y (inverted because SVG y-down)
    px = (lon + 180) / 360 * MAP_W
    py = (90 - lat) / 180 * MAP_H
    return (round(px, 2), round(py, 2))


_ANTIMERIDIAN_X_GAP = MAP_W * 0.5  # 400px — segment longer than this wraps the antimeridian


def ring_to_path(arcs: list[list[int]], topo: dict, transform: dict, reverse: bool = False) -> str:
    """Convert one ring (list of arc indices, possibly negated) to an SVG path.

    Splits the ring into multiple subpaths (`M ... Z`) at any segment
    that spans more than half the viewBox width — those are antimeridian
    wraps (Russia, Fiji) that would otherwise draw a horizontal line all
    the way across the map.
    """
    points: list[tuple[float, float]] = []
    for arc_index in arcs:
        if arc_index < 0:
            arc = list(reversed(decode_arc(topo["arcs"][~arc_index])))
        else:
            arc = decode_arc(topo["arcs"][arc_index])
        for x_q, y_q in arc:
            points.append(project(x_q, y_q, transform))
    if not points:
        return ""

    # Segment the point list at antimeridian crossings: any consecutive
    # pair whose x-distance exceeds half the viewBox starts a new subpath.
    subpaths: list[list[tuple[float, float]]] = [[points[0]]]
    for prev, curr in zip(points, points[1:]):
        if abs(curr[0] - prev[0]) > _ANTIMERIDIAN_X_GAP:
            subpaths.append([curr])
        else:
            subpaths[-1].append(curr)

    parts: list[str] = []
    for sub in subpaths:
        if not sub:
            continue
        parts.append(f"M{sub[0][0]} {sub[0][1]}")
        for x, y in sub[1:]:
            parts.append(f"L{x} {y}")
        parts.append("Z")
    return "".join(parts)


def feature_to_paths(geom: dict, topo: dict, transform: dict) -> list[str]:
    """A geometry can be Polygon, MultiPolygon, etc. Return all rings as paths."""
    paths: list[str] = []
    if geom["type"] == "Polygon":
        for ring in geom["arcs"]:
            paths.append(ring_to_path(ring, topo, transform))
    elif geom["type"] == "MultiPolygon":
        for poly in geom["arcs"]:
            for ring in poly:
                paths.append(ring_to_path(ring, topo, transform))
    return [p for p in paths if p]


def main() -> int:
    topo = fetch_topo()
    transform = topo["transform"]
    countries = topo["objects"]["countries"]["geometries"]

    print(f"Converting {len(countries)} country geometries to SVG...")

    svg_paths: list[str] = []
    seen_codes: set[str] = set()
    unmapped: list[str] = []
    for country in countries:
        numeric = country.get("id", "")
        # Pad to 3 digits for the lookup
        numeric_padded = str(numeric).zfill(3)
        code = NUMERIC_TO_ALPHA2.get(numeric_padded)
        if not code:
            unmapped.append(numeric_padded)
            continue
        seen_codes.add(code)

        d_path = " ".join(feature_to_paths(country, topo, transform))
        if not d_path:
            continue
        svg_paths.append(
            f'<path id="{code}" data-country="{code}" d="{d_path}"/>'
        )

    print(f"  Mapped: {len(seen_codes)}.  Unmapped numeric IDs: {len(unmapped)} ({unmapped[:8]}...)")

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {MAP_W} {MAP_H}" '
        'preserveAspectRatio="xMidYMid meet" class="world-map">'
        '<rect width="100%" height="100%" fill="var(--map-bg, transparent)"/>'
        + "".join(svg_paths)
        + "</svg>"
    )

    OUT_PATH.write_text(svg + "\n")
    print(f"Wrote {OUT_PATH} ({len(svg):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
