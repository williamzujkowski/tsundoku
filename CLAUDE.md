# Tsundoku — Project Conventions

## Quick Reference

```bash
npm run dev          # Start dev server
npm run build        # Generate stats + search index + build
npm run typecheck    # Type check Astro/TypeScript
npm test             # Run unit tests (vitest)
npm run test:watch   # Run tests in watch mode
python3 scripts/enrich.py --limit 100    # Enrich books (Open Library + Google Books)
python3 scripts/enrich-authors.py --limit 100  # Enrich authors (Wikipedia)
python3 scripts/enrich-gutenberg.py --limit 500  # Link to Project Gutenberg
```

## Architecture

- **Astro** static site generator with content collections
- **Svelte 5** for interactive islands (search modal, book grid)
- **Tailwind CSS 4** for styling
- **Vitest** for unit testing
- **Content**: JSON files in `src/content/books/` and `src/content/authors/`
- **Data pipeline**: Python scripts for enrichment, stats, reading status

## Core Principles

```
correctness > simplicity > performance > cleverness
```

- **DRY**: Shared utilities in `src/utils/formatting.ts` — `toSlug()`, `priorityLabel()`, `priorityClass()`, `statusLabel()`, `statusClass()`, `pluralize()`
- **TDD**: Write tests alongside utility code. Tests live next to source (`*.test.ts`)
- **YAGNI**: Only build what's needed now
- **No `any`**: Use proper types

## Shared Utilities

All formatting/display logic lives in `src/utils/formatting.ts`:

| Function | Purpose |
|---|---|
| `toSlug(text)` | Text → URL slug (lowercase, hyphenated) |
| `priorityLabel(p)` | Priority number → display label |
| `priorityClass(p)` | Priority number → full CSS class string |
| `priorityBadgeClass(p)` | Priority number → compact badge CSS |
| `statusLabel(s)` | Reading status → display label with icon |
| `statusClass(s)` | Reading status → CSS class string |
| `statusColor(s)` | Reading status → text color class |
| `statusIcon(s)` | Reading status → icon character |
| `pluralize(n, s)` | Count-aware singular/plural |

**Never** duplicate these in page files. Import from the utility module.

## Data Sources (trust hierarchy)

1. **Seed CSV** (`data/seed.csv`) — canonical book list
2. **Open Library** — covers, first published year, author data, OCLC IDs
3. **Google Books** — descriptions, ISBNs, page counts, categories
4. **Wikipedia** — author bios and photos
5. **Project Gutenberg** (via Gutendex) — free reading links
6. **HathiTrust** — digitized full texts (via OCLC/ISBN lookup)
7. **WorldCat** — library catalog links (via OCLC ID)

## Key Patterns

- All books must have `language: "eng"`
- Reading status tracked in `data/reading-status.csv` (edit CSV, rebuild)
- Stats auto-generated at build time (`src/data/stats.json`)
- Search index auto-generated at build time (`public/search-index.json`)
- All internal links use `import.meta.env.BASE_URL` prefix
- Gutenberg matching requires **both** author AND title match
- Footer stats sourced from `stats.json` (not hardcoded)

## Build Pipeline

```
apply-reading-status.py → generate-stats.py → generate-search-index.py → astro build
```

## CI/CD

- **Quality gate**: typecheck + tests must pass before build
- **Deploy**: GitHub Pages via `deploy.yml` workflow

## Content Schema

Books: title, author, category, priority (1-3), slug, tags, description?,
cover_url?, isbn?, first_published?, subjects?, pages?, gutenberg_url?,
oclc_id?, worldcat_url?, hathitrust_url?, reading_status? (want/reading/read)

Authors: name, slug, bio?, photo_url?, wikipedia_url?, birth_year?, death_year?, book_count
