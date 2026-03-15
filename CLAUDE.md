# Tsundoku — Project Conventions

## Quick Reference

```bash
npm run dev          # Start dev server
npm run build        # Generate stats + search index + build
npm run typecheck    # Type check Astro/TypeScript
python3 scripts/enrich.py --limit 100    # Enrich books (Open Library + Google Books)
python3 scripts/enrich-authors.py --limit 100  # Enrich authors (Wikipedia)
python3 scripts/enrich-gutenberg.py --limit 500  # Link to Project Gutenberg
```

## Architecture

- **Astro** static site generator with content collections
- **Svelte 5** for interactive islands (search modal, book grid)
- **Tailwind CSS 4** for styling
- **Content**: JSON files in `src/content/books/` and `src/content/authors/`
- **Data pipeline**: Python scripts for enrichment, stats, reading status

## Data Sources (trust hierarchy)

1. **Seed CSV** (`data/seed.csv`) — canonical book list
2. **Open Library** — covers, first published year, author data
3. **Google Books** — descriptions, ISBNs, page counts, categories
4. **Wikipedia** — author bios and photos
5. **Project Gutenberg** (via Gutendex) — free reading links

## Key Patterns

- All books must have `language: "eng"`
- Reading status tracked in `data/reading-status.csv` (edit CSV, rebuild)
- Stats auto-generated at build time (`src/data/stats.json`)
- Search index auto-generated at build time (`public/search-index.json`)
- All internal links use `import.meta.env.BASE_URL` prefix
- Gutenberg matching requires **both** author AND title match

## Build Pipeline

```
apply-reading-status.py → generate-stats.py → generate-search-index.py → astro build
```

## Content Schema

Books: title, author, category, priority (1-3), slug, tags, description?,
cover_url?, isbn?, first_published?, subjects?, pages?, gutenberg_url?,
reading_status? (want/reading/read)

Authors: name, slug, bio?, photo_url?, wikipedia_url?, birth_year?, book_count
