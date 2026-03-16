import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

const books = defineCollection({
  loader: glob({ pattern: '**/*.json', base: './src/content/books' }),
  schema: z.object({
    title: z.string(),
    author: z.string(),
    category: z.string(),
    priority: z.number().int().min(1).max(3),
    slug: z.string(),
    tags: z.array(z.string()).default([]),
    // Enrichment fields (optional — populated by scripts/enrich.py)
    description: z.string().optional(),
    cover_url: z.string().optional(),
    cover_url_large: z.string().optional(),
    open_library_url: z.string().optional(),
    isbn: z.string().optional(),
    first_published: z.number().optional(),
    subjects: z.array(z.string()).optional(),
    pages: z.number().optional(),
    language: z.string().optional(),
    google_books_url: z.string().optional(),
    // Gutenberg fields (populated by scripts/enrich-gutenberg.py)
    gutenberg_id: z.number().optional(),
    gutenberg_url: z.string().optional(),
    gutenberg_read_url: z.string().optional(),
    // Library identifiers (from BookReconciler-style enrichment)
    oclc_id: z.string().optional(),
    lccn: z.string().optional(),
    worldcat_url: z.string().optional(),
    hathitrust_url: z.string().optional(),
    hathitrust_rights: z.string().optional(),
    // LibriVox (populated by scripts/enrich-librivox.py)
    librivox_url: z.string().optional(),
    // Standard Ebooks (populated by scripts/enrich-standardebooks.py)
    standardebooks_url: z.string().optional(),
    // Internet Archive
    archive_url: z.string().optional(),
    // Copyright status (computed by scripts/enrich-copyright.py from existing metadata)
    copyright_status: z.enum(['public_domain', 'likely_public_domain', 'in_copyright', 'undetermined']).optional(),
    // Reading status (from data/reading-status.csv — owner's reading progress)
    reading_status: z.enum(['want', 'reading', 'read']).optional(),
    status_date: z.string().optional(),
    status_notes: z.string().optional(),
  }),
});

const authors = defineCollection({
  loader: glob({ pattern: '**/*.json', base: './src/content/authors' }),
  schema: z.object({
    name: z.string(),
    slug: z.string(),
    bio: z.string().optional(),
    photo_url: z.string().optional(),
    wikipedia_url: z.string().optional(),
    open_library_url: z.string().optional(),
    birth_year: z.number().optional(),
    death_year: z.number().optional(),
    book_count: z.number(),
  }),
});

export const collections = { books, authors };
