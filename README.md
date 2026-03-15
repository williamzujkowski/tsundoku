# 積ん読 Tsundoku

A curated bookshelf with reading tracker — because buying books and not reading them is a lifestyle.

**Tsundoku** (積ん読) is the Japanese word for acquiring books and letting them pile up without reading them.

**Live site:** [williamzujkowski.github.io/tsundoku](https://williamzujkowski.github.io/tsundoku/)

## Features

- Browse books with cover art, descriptions, and metadata
- Global search (⌘K) across books and authors
- Filter by category, priority, and reading status
- Individual book pages with covers, descriptions, ISBNs, page counts
- Author pages with Wikipedia bios and photos
- Reading progress tracker (want to read / reading / read)
- "Read free" links to Project Gutenberg for public domain works
- External links: Goodreads, Google Books, Open Library, WorldCat
- Stats dashboard with enrichment coverage and reading progress
- Static site — no server, no database, deploys to GitHub Pages

## Tech Stack

- [Astro](https://astro.build) — static site framework with content collections
- [Svelte 5](https://svelte.dev) — interactive islands (search, book grid)
- [Tailwind CSS 4](https://tailwindcss.com) — utility-first styling
- Zod schema validation on all content

## Data Sources

| Source | What it provides |
|--------|-----------------|
| Open Library | Covers, first published year, author data |
| Google Books | Descriptions, ISBNs, page counts, categories |
| Wikipedia | Author bios and photos |
| Gutendex | Project Gutenberg free reading links |

## Development

```bash
npm install
npm run dev        # Start dev server
npm run build      # Generate stats + search index + build
npm run typecheck  # Type check
```

## Reading Status

Edit `data/reading-status.csv` to track your reading progress:

```csv
slug,status,date_updated,notes
dune,read,2024-06-15,Classic sci-fi
neuromancer,reading,,Currently on chapter 3
```

Status values: `want` | `reading` | `read`

## Enrichment Scripts

```bash
python3 scripts/enrich.py --limit 100           # Book covers + descriptions
python3 scripts/enrich-authors.py --limit 100    # Author bios + photos
python3 scripts/enrich-gutenberg.py --limit 500  # Gutenberg free reading links
python3 scripts/generate-stats.py                # Regenerate stats
python3 scripts/generate-search-index.py         # Regenerate search index
```

## License

MIT
