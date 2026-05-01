# Tsundoku — Project Conventions

## Quick Reference

```bash
# Development
npm run dev          # Start dev server
npm run build        # Full build (prebuild + astro build)
npm run typecheck    # Type check Astro/TypeScript
npm test             # Run unit tests (vitest)
npm run test:watch   # Run tests in watch mode

# Enrichment (see scripts/README.md for full inventory)
python3 scripts/run-all-enrichments.py           # Auto-scan all sources to completion
python3 scripts/run-all-enrichments.py --status  # Show scan progress
python3 scripts/enrich-gaps.py --report          # Show data gap report
python3 scripts/enrich-copyright.py --report     # Show copyright distribution
python3 scripts/enrich-categories.py --report    # Show category distribution

# Python tests
cd scripts && python3 -m pytest -q
```

## Architecture

- **Astro 6** static site generator with content collections
- **Svelte 5** for interactive islands (search, book grid, random book, share)
- **Tailwind CSS 4** for styling
- **Vitest** for JS unit testing, **pytest** for Python unit testing
- **Content**: JSON files in `src/content/books/` and `src/content/authors/`
- **Data pipeline**: Python scripts for enrichment, stats, reading status
- **State tracking**: Enrichment scripts resume from last position via `enrichment_state.py`

## Svelte Islands

| Component | Purpose | Hydration |
|---|---|---|
| `SearchModal.svelte` | Global search with keyboard nav (⌘K, arrow keys) | `client:idle` |
| `BookGrid.svelte` | Filterable/searchable book grid on browse page | `client:load` |
| `RandomBook.svelte` | Random book discovery button in nav | `client:idle` |
| `ShareButton.svelte` | Web Share API + clipboard fallback on book detail | `client:idle` |

## Core Principles

```
correctness > simplicity > performance > cleverness
```

- **DRY**: Shared utilities in `src/utils/formatting.ts`, shared Python matching in `scripts/matching.py`
- **TDD**: Tests live next to source (`*.test.ts`, `test_*.py`)
- **YAGNI**: Only build what's needed now
- **No `any`**: Use proper TypeScript types
- **Template Method**: Enrichment scripts extend `EnrichmentScript` base class

## Shared Utilities

**TypeScript** (`src/utils/formatting.ts`):

| Function | Purpose |
|---|---|
| `toSlug(text)` | Text → URL slug (lowercase, hyphenated) |
| `priorityLabel(p)` | Priority number → display label |
| `priorityClass(p)` / `priorityBadgeClass(p)` | Priority → CSS classes |
| `statusLabel(s)` / `statusClass(s)` / `statusIcon(s)` | Reading status → display |
| `thumbnailUrl(url)` | Open Library -M.jpg → -S.jpg for grid thumbnails |
| `seededShuffle(items, seed?)` | Deterministic shuffle (daily featured rotation) |
| `pluralize(n, s)` | Count-aware singular/plural |

**Python** (`scripts/matching.py`):

| Function | Purpose |
|---|---|
| `title_similarity(a, b)` | Word overlap ratio between titles |
| `titles_match(query, result)` | Containment or overlap match check |
| `strip_article(title)` | Remove leading A/An/The |
| `author_last_name(author)` | Extract last name for fuzzy matching |

## Enrichment Pipeline

All enrichment scripts extend `EnrichmentScript` base class and use shared state tracking.
See **[scripts/README.md](scripts/README.md)** for the full script inventory.

### Auto-resume runner

```bash
python3 scripts/run-all-enrichments.py           # Scan all sources until complete
python3 scripts/run-all-enrichments.py --status   # Show scan positions
```

The runner loops subjects → gutenberg → librivox → hathitrust in batches of 500.
Safety: max 20 iterations, 10s inter-batch delays. State persisted in `data/enrichment-state.json` (gitignored).

### Post-enrichment

After enrichment scans, always run:
```bash
python3 scripts/enrich-copyright.py --apply    # Recompute copyright status
python3 scripts/enrich-categories.py           # Check for category suggestions
python3 scripts/generate-stats.py              # Update stats
python3 scripts/generate-search-index.py       # Update search index
```

### Copyright status

Computed from existing metadata (no API calls):

| Status | Rule |
|---|---|
| `public_domain` | Gutenberg/LibriVox present, HathiTrust pd/pdus, or published ≤ 1930 |
| `likely_public_domain` | Published 1931-1963 (many copyrights unrenewed) |
| `in_copyright` | Published > 1963 (unless other PD signal) |
| `undetermined` | No publication year or other signal |

## Data Sources (trust hierarchy)

1. **Seed CSV** (`data/seed.csv`) — canonical book list
2. **Open Library** — covers, year, subjects, OCLC, page counts
3. **Google Books** — descriptions, ISBNs, categories
4. **Wikipedia** — author bios and photos
5. **Project Gutenberg** (Gutendex) — free reading links (public domain only)
6. **LibriVox** — free audiobook links (public domain only)
7. **HathiTrust** — digitized full texts + rights metadata
8. **WorldCat** — library catalog links (via OCLC ID)

## Key Patterns

- All books must have `language: "eng"`
- Reading status tracked in `data/reading-status.csv` (edit CSV, rebuild)
- Stats auto-generated at build time (`src/data/stats.json`)
- Search index auto-generated at build time (`public/search-index.json`)
- All internal links use `import.meta.env.BASE_URL` prefix
- Enrichment matching requires **both** author AND title match
- LibriVox: strip leading articles and lowercase before search
- JSON-LD Book/Person schemas on detail pages
- og:image meta tags on book (cover) and author (photo) pages
- Copyright/public domain badges on book detail pages
- View transitions + prefetch enabled for smooth navigation
- Thumbnail optimization: `-S.jpg` for grid covers, `-M.jpg`/`-L.jpg` for detail

## Canonical Paths

| Concern | Path |
|---|---|
| **Book data** | `src/content/books/*.json` |
| **Author data** | `src/content/authors/*.json` |
| **Content schema** | `src/content.config.ts` |
| **Reading status** | `data/reading-status.csv` |
| **Build stats** | `src/data/stats.json` |
| **Search index** | `public/search-index.json` |
| **Shared formatting** | `src/utils/formatting.ts` |
| **Enrichment base** | `scripts/enrichment_base.py` |
| **Enrichment config** | `scripts/enrichment_config.py` |
| **Enrichment state** | `scripts/enrichment_state.py` (+ `data/enrichment-state.json`) |
| **Title matching** | `scripts/matching.py` |
| **Additive JSON merge** | `scripts/json_merge.py` (never overwrites non-empty fields — see #90) |
| **Enrichment runner** | `scripts/run-all-enrichments.py` |
| **Data integrity tests** | `scripts/test_data_integrity.py` |
| **CI workflow** | `.github/workflows/deploy.yml` |
| **Script inventory** | `scripts/README.md` |

## Error Handling (Enrichment)

Enrichment scripts classify errors via `enrichment_base.py`:

| Error Type | HTTP Code | Action | Retry? |
|---|---|---|---|
| `not_found` | 404 | Skip permanently | No |
| `rate_limited` | 429 | Log + skip batch | Next day |
| `connection_error` | timeout/DNS | Log + continue | Yes |
| `parse_error` | — | Log malformed response | No |
| `search_error` | — | Log + continue | Yes |

Errors logged to `data/enrichment-errors.jsonl` (gitignored). Review with:
```bash
cat data/enrichment-errors.jsonl | python3 -m json.tool
```

## Build Pipeline

```
apply-reading-status.py → generate-author-stubs.py → generate-stats.py → generate-search-index.py → astro build
```

## CI/CD

- **Quality gate**: typecheck + tests must pass before build
- **Deploy**: GitHub Pages via `deploy.yml` workflow
- **Dependabot**: weekly npm + GitHub Actions updates
- **CODEOWNERS**: @williamzujkowski

## Content Schema

**Books**: title, author, category, priority (1-3), slug, tags,
description?, cover_url?, cover_url_large?, isbn?, first_published?,
subjects?, pages?, language?, gutenberg_url?, gutenberg_id?,
gutenberg_read_url?, librivox_url?,
oclc_id?, lccn?, worldcat_url?, hathitrust_url?, hathitrust_rights?,
copyright_status?, reading_status?

**Authors**: name, slug, bio?, photo_url?, wikipedia_url?,
open_library_url?, birth_year?, death_year?, book_count

## Skills

| Skill | Trigger | Purpose |
|---|---|---|
| `enrichment` | "enrich", "scan books" | Run enrichment pipeline with status checks |
| `data-quality` | "data quality", "coverage report" | Review data completeness and gaps |
