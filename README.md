# 積ん読 Tsundoku

A curated bookshelf with reading tracker — because buying books and not reading them is a lifestyle.

**Tsundoku** (積ん読) is the Japanese word for acquiring books and letting them pile up without reading them.

**Live site:** [williamzujkowski.github.io/tsundoku](https://williamzujkowski.github.io/tsundoku/)

## Features

- **3,534 books** across **29 categories** from **1,616 authors**
- Browse with cover art, descriptions, and metadata
- Global search (⌘K) with keyboard navigation across books and authors
- Filter by category, priority, reading status, and genre tags (35 genres)
- Individual book pages with JSON-LD structured data, og:image social previews
- Author pages with Wikipedia bios, photos, and book listings
- Reading progress tracker (want to read / reading / read)
- Free reading/listening links: 1,003 Project Gutenberg, 717 LibriVox audiobooks, 134 HathiTrust
- External links: Goodreads, Google Books, Open Library, WorldCat
- Copyright status badges (public domain / likely public domain / in copyright)
- Stats dashboard with bookshelf metrics (total pages, reading hours, shelf space)
- Random book discovery button, Web Share API sharing
- View transitions + prefetch for instant navigation
- Sitemap with 5,000+ URLs for SEO
- Static site — no server, no database, deploys to GitHub Pages

## Tech Stack

- [Astro 6](https://astro.build) — static site framework with content collections
- [Svelte 5](https://svelte.dev) — interactive islands (search, book grid, random, share)
- [Tailwind CSS 4](https://tailwindcss.com) — utility-first styling
- [Vitest](https://vitest.dev) — JavaScript testing (35 tests)
- [pytest](https://pytest.org) — Python testing (35 tests)
- 70 total tests across both languages, gated in CI
- Zod schema validation on all content

## Data Sources

| Source | What it provides |
|--------|-----------------|
| Open Library | Covers, subjects, page counts, ISBNs, OCLC IDs |
| Google Books | Descriptions, ISBNs, categories |
| Wikipedia | Author bios and photos |
| Project Gutenberg | Free reading links (public domain) |
| LibriVox | Free audiobook links (public domain) |
| HathiTrust | Digitized full texts + rights metadata |
| WorldCat | Library catalog links |

## Development

```bash
npm install
npm run dev        # Start dev server
npm run build      # Full build (prebuild + astro build)
npm run typecheck  # Type check
npm test           # Run JS tests
```

## Enrichment

Multi-source enrichment pipeline with state tracking and auto-resume:

```bash
# Full automated scan (all sources, resumes from last position)
python3 scripts/run-all-enrichments.py

# Check scan progress
python3 scripts/run-all-enrichments.py --status

# Show data gaps
python3 scripts/enrich-gaps.py --report

# After enrichment, recompute copyright status
python3 scripts/enrich-copyright.py --apply
```

See [scripts/README.md](scripts/README.md) for the complete script inventory.

## Reading Status

Edit `data/reading-status.csv` to track your reading progress:

```csv
slug,status,date_updated,notes
dune,read,2024-06-15,Classic sci-fi
neuromancer,reading,,Currently on chapter 3
```

Status values: `want` | `reading` | `read`

## License

MIT
