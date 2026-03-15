# 積ん読 Tsundoku

A curated bookshelf of 3,526 essential works across 42 categories. Built with Astro, Svelte 5, and Tailwind CSS 4.

**Tsundoku** (積ん読) is the Japanese word for acquiring books and letting them pile up without reading them. This app turns that habit into a browsable, searchable collection.

## Features

- Browse 3,526 books across 42 categories
- Search by title or author
- Filter by category and priority level (P1 Must-Read, P2 Recommended, P3 Supplementary)
- Category and author index pages
- Dark theme with Material Design 3 color tokens
- Static site generation — no server required

## Tech Stack

- [Astro 6](https://astro.build) — static site framework
- [Svelte 5](https://svelte.dev) — interactive islands (search/filter)
- [Tailwind CSS 4](https://tailwindcss.com) — utility-first styling
- Content Collections with JSON loader

## Development

```bash
# Install dependencies
npm install

# Start dev server
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

## Data

The book data lives in `src/content/books/` as individual JSON files, generated from `data/seed.csv` via:

```bash
python3 scripts/import-csv.py
```

Each book has: title, author, category, priority (1-3), slug, and tags.

## License

MIT
