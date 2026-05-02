# Scripts

Canonical inventory of all Python scripts. Referenced by CLAUDE.md and README.md.

## Enrichment Runner

| Script | Purpose |
|---|---|
| `run-all-enrichments.py` | Auto-resume runner — loops all enrichment scripts until complete. `--status` shows scan positions. |

## Data Enrichment (source-specific)

| Script | Source | What it adds |
|---|---|---|
| `enrich.py` | Open Library + Google Books | Covers, descriptions, ISBNs, page counts, subjects, first published year |
| `enrich-ol-classification.py` | Open Library | DDC, LCC, ISBN, subject_facet, language, pages, first_published year (work-level) |
| `enrich-ol-fuzzy-retry.py` | Open Library | Multi-strategy fuzzy retry for books missing classification |
| `enrich-ol-firstedition.py` | Open Library | First-edition anchor: editions consensus, original_*, representative_edition |
| `enrich-wikidata-book.py` | Wikidata SPARQL | Year corrections, original_publisher, awards, series via P648 |
| `enrich-wikidata-author.py` | Wikidata SPARQL | Nationality, alternate names, movements, awards, VIAF via P648 |
| `recategorize.py` | Internal (DDC/LCC + tags) | Computes category from DDC/LCC primary, falls back to tag heuristics |
| `enrich-gutenberg.py` | Project Gutenberg (Gutendex) | Free reading links for public domain books |
| `enrich-librivox.py` | LibriVox | Free audiobook links for public domain books |
| `enrich-hathitrust.py` | HathiTrust | Digitized text links (via OCLC/ISBN lookup) |
| `enrich-authors.py` | Wikipedia + Open Library | Author bios, photos, birth/death years |
| `enrich-gaps.py` | Open Library + Google Books | Multi-source gap filler — fills missing fields with fallback |
| `enrich-copyright.py` | Internal (metadata) | Computes copyright_status from existing fields (no API calls) |
| `enrich-tags.py` | Internal (subjects) | Maps Open Library subjects to normalized genre tags (35 genres) |
| `enrich-wikipedia-books.py` | Wikipedia | Descriptions + covers for books missing them |
| `enrich-descriptions.py` | OL works + editions, Google Books, Gutenberg | Consolidated five-strategy fallback for missing descriptions |

## Build Pipeline (run automatically by `npm run build`)

| Script | Purpose |
|---|---|
| `apply-reading-status.py` | Merges `data/reading-status.csv` into book JSON files |
| `generate-author-stubs.py` | Creates minimal author pages for any author without one |
| `generate-stats.py` | Generates `src/data/stats.json` with collection statistics |
| `generate-search-index.py` | Generates `public/search-index.json` for client-side search |

## Data Import (one-time use)

| Script | Purpose |
|---|---|
| `import-csv.py` | Initial import of books from `data/seed.csv` to JSON |
| `merge-google-library.py` | Merge Google Play Books library export into collection |
| `dedupe-books.py` | Find and merge duplicate books (article/edition variants) |
| `update-readme-stats.py` | Inject current stats from stats.json into README.md |

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

| File | Tests |
|---|---|
| `test_matching.py` | 27 tests for title similarity, slug generation, author matching |
| `test_enrichment.py` | 8 tests for state tracking, config validation |
| `test_json_merge.py` | 18 tests for additive merge invariants |
| `test_http_cache.py` | 12 tests for hit/miss/expire/negative-cache/persistence |
| `test_validate_photo_urls.py` | 7 tests for HEAD-probe classification + apply mode |
| `test_cache_photos.py` | 19 tests for content-type → ext, idempotency, JSON rewrite |
| `test_author_sources.py` | 20 tests for Open Library author page + Wikidata + name variants |

## Usage

```bash
# Full automated pipeline (API scans + post-enrichment + stats)
python3 scripts/run-all-enrichments.py

# Check enrichment status
python3 scripts/run-all-enrichments.py --status

# The runner automatically executes this full pipeline:
# Phase 1 (API): subjects → gutenberg → librivox → hathitrust
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
