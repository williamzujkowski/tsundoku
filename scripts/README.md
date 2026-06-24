# Scripts

Canonical inventory of all Python scripts. Referenced by CLAUDE.md and README.md.

## Enrichment Runner

| Script | Purpose |
|---|---|
| `run-all-enrichments.py` | Auto-resume runner — loops all enrichment scripts until complete. `--status` shows scan positions. |

## Data Enrichment (source-specific)

| Script | Source | What it adds |
|---|---|---|
| `enrich-ol-classification.py` | Open Library | DDC, LCC, ISBN, subject_facet, language, pages, first_published year (work-level) |
| `enrich-ol-fuzzy-retry.py` | Open Library | Multi-strategy fuzzy retry for books missing classification |
| `enrich-ol-firstedition.py` | Open Library | First-edition anchor: editions consensus, original_*, representative_edition |
| `enrich-wikidata-book.py` | Wikidata SPARQL | Year corrections, original_publisher, awards, series via P648 |
| `enrich-wikidata-author.py` | Wikidata SPARQL | Nationality, alternate names, movements, awards, VIAF via P648 |
| `enrich-adaptations.py` | Wikidata SPARQL | `adaptations` (film/tv/stage/radio/opera/other) via P144 "based on" — batched, resumable (#184) |
| `recategorize.py` | Internal (DDC/LCC + tags) | Computes category from DDC/LCC primary, falls back to tag heuristics |
| `enrich-gutenberg.py` | Project Gutenberg (Gutendex) | Free reading links for public domain books |
| `enrich-librivox.py` | LibriVox | Free audiobook links for public domain books |
| `enrich-hathitrust.py` | HathiTrust | Digitized text links (via OCLC/ISBN lookup) |
| `enrich-authors.py` | Wikipedia + Open Library | Author bios, photos, birth/death years |
| `enrich-gaps.py` | Open Library + Google Books | Multi-source gap filler — fills missing fields with fallback |
| `enrich-copyright.py` | Internal (metadata) | Computes copyright_status from existing fields (no API calls) |
| `enrich-tags.py` | Internal (subjects) | Maps Open Library subjects to normalized genre tags (35 genres) |
| `enrich-wikipedia-books.py` | Wikipedia | Narrow first description pass; uniquely also fills a missing cover_url. Runs in `run-all` before `enrich-descriptions.py` |
| `enrich-descriptions.py` | OL works + editions, Google Books, OL first_sentence, Gutenberg | **Canonical description path** (#184) — consolidated five-strategy fallback, wired into `run-all-enrichments.py` as the last description pass |

## Build Pipeline (run automatically by `npm run build`)

| Script | Purpose |
|---|---|
| `apply-reading-status.py` | Merges `data/reading-status.csv` into book JSON files |
| `generate-author-stubs.py` | Creates minimal author pages for any author without one; refreshes `book_count` on every existing record (#179) |
| `generate-stats.py` | Generates `src/data/stats.json` with collection statistics |
| `generate-search-index.py` | Generates `public/search-index.json` for client-side search |
| `generate-browse-data.py` | Generates the browse-page data fetched on hydrate (#99) |

`build-world-map-svg.py` is a standalone asset generator (run manually, not part of `prebuild`): it regenerates `src/data/world-map.svg`, which `src/pages/stats.astro` renders.

## Data Import (one-time use)

| Script | Purpose |
|---|---|
| `import-csv.py` | Initial import of books from `data/seed.csv` to JSON |
| `merge-google-library.py` | Merge Google Play Books library export into collection |
| `dedupe-books.py` | Find and merge duplicate books (article/edition variants) |
| `update-readme-stats.py` | Inject current stats from stats.json into README.md |

## Completed migrations (spent — do not re-run blindly)

These ran once; their effects are already baked into the content. They have
zero inbound references and are kept for reference only. Several embed
hand-curated tables or heuristics — re-running without a fresh audit can
corrupt data. Treat as historical.

| Script | What it did |
|---|---|
| `dedupe-authors-by-diacritic.py` | One-time merge of 5 near-duplicate author pairs differing only by diacritics |
| `fix-ancient-work-years.py` | Hand-audited `first_published` years for ancient works (uses a hardcoded table) |
| `fix-non-english-descriptions.py` | One-time cleanup of ~17 non-English descriptions |
| `derive-classification.py` | One-time DDC/LCC classification backfill (tagged with `derived_v1` provenance) |

## Shared Modules

| Module | Purpose |
|---|---|
| `enrichment_base.py` | Base class for enrichment scripts (Template Method pattern) |
| `enrichment_config.py` | Centralized rate limits, API URLs, timeouts |
| `enrichment_state.py` | State tracking — resume, daily resets, completion detection |
| `matching.py` | Shared title/author matching logic (word overlap, article stripping) |
| `json_merge.py` | Additive JSON merge — never overwrites non-empty fields (issue #90) |
| `http_cache.py` | SQLite-backed HTTP response cache; per-source TTLs + negative caching (issue #91) |
| `author_sources.py` | Per-source enrichment functions (Open Library author page, Wikidata) + name-variant generator (issue #105) |

## Maintenance

| Script | Purpose |
|---|---|
| `validate-photo-urls.py` | HEAD-probe `photo_url` / `cover_url` and clear confirmed-dead ones (issue #93). Default is dry-run; pass `--apply` to actually clear. |
| `cache-photos.py` | Download author photos / book covers to `public/cached/` and rewrite source JSON URLs to local paths. Originals preserved in `*_source` fields (issue #94). |
| `enrich-authors-gaps.py` | Fill missing bio / photo on existing authors via multi-source fallback (Open Library author page → Wikidata). Additive — never overwrites (issue #105). |

## Tests

All `scripts/test_*.py` are auto-discovered by `pytest` (CI runs `cd scripts && python3 -m pytest -q`). Run the full suite before committing pipeline changes. Highlights:

| File | Tests |
|---|---|
| `test_matching.py` | title similarity, slug generation, author matching (incl. empty-title guard) |
| `test_enrichment.py` | state tracking, config validation |
| `test_json_merge.py` | additive merge invariants |
| `test_http_cache.py` | hit/miss/expire/negative-cache/persistence |
| `test_http_retry.py` | backoff, Retry-After parsing, http(s)-only scheme allowlist |
| `test_validate_photo_urls.py` | HEAD-probe classification + apply mode |
| `test_cache_photos.py` | content-type → ext, idempotency, JSON rewrite |
| `test_author_sources.py` | Open Library author page + Wikidata + name variants |
| `test_enrich_copyright.py` | copyright-status rule precedence (platform > HathiTrust > year) |
| `test_data_integrity.py` | content invariants (slugs, required fields, author book_count, ...) |

…plus `test_book_sources`, `test_edition_date`, `test_parallel_fetch`, `test_wikidata`, `test_dedupe_books`, `test_enrich_ol_firstedition`, `test_enrich_wikipedia_books`, `test_merge_google_library`, `test_recategorize_classification`.

## Usage

```bash
# Full automated pipeline (API scans + post-enrichment + stats)
python3 scripts/run-all-enrichments.py

# Check enrichment status
python3 scripts/run-all-enrichments.py --status

# The runner automatically executes this full pipeline:
# Phase 1 (API): subjects → gutenberg → librivox → hathitrust → wikipedia_books → descriptions
# Phase 2 (post): tags → copyright → categories → dedupe → stubs → stats → index
```

### Manual operations

```bash
# Fill specific gaps
python3 scripts/enrich-gaps.py --report
python3 scripts/enrich-gaps.py --limit 500 --field subjects

# Recompute copyright/tags/categories independently
python3 scripts/enrich-copyright.py --apply
python3 scripts/enrich-tags.py --apply
python3 scripts/recategorize.py --apply
```
