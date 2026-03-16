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
| `enrich-gutenberg.py` | Project Gutenberg (Gutendex) | Free reading links for public domain books |
| `enrich-librivox.py` | LibriVox | Free audiobook links for public domain books |
| `enrich-hathitrust.py` | HathiTrust | Digitized text links (via OCLC/ISBN lookup) |
| `enrich-authors.py` | Wikipedia + Open Library | Author bios, photos, birth/death years |
| `enrich-gaps.py` | Open Library + Google Books | Multi-source gap filler — fills missing fields with fallback |
| `enrich-categories.py` | Internal (subjects) | Suggests category changes based on subject keywords |
| `enrich-copyright.py` | Internal (metadata) | Computes copyright_status from existing fields (no API calls) |

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

## Shared Modules

| Module | Purpose |
|---|---|
| `enrichment_base.py` | Base class for enrichment scripts (Template Method pattern) |
| `enrichment_config.py` | Centralized rate limits, API URLs, timeouts |
| `enrichment_state.py` | State tracking — resume, daily resets, completion detection |
| `matching.py` | Shared title/author matching logic (word overlap, article stripping) |

## Tests

| File | Tests |
|---|---|
| `test_matching.py` | 27 tests for title similarity, slug generation, author matching |
| `test_enrichment.py` | 8 tests for state tracking, config validation |

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
python3 scripts/enrich-categories.py --apply
```
