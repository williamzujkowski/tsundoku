import { defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';
import { z } from 'astro/zod';

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
    // Copyright status (computed by scripts/enrich-copyright.py from existing metadata)
    copyright_status: z.enum(['public_domain', 'likely_public_domain', 'in_copyright', 'undetermined']).optional(),
    // Reading status (from data/reading-status.csv — owner's reading progress)
    reading_status: z.enum(['want', 'reading', 'read']).optional(),
    // Local cover cache (populated by scripts/cache-photos.py — see #94)
    // When set, cover_url / cover_url_large point to a local /cached/ path
    // and the *_source fields preserve the original upstream URL for attribution.
    cover_url_source: z.string().optional(),
    cover_url_large_source: z.string().optional(),
    cover_cached_at: z.string().optional(),
    // Open Library classification (populated by scripts/enrich-ol-classification.py)
    // ddc = Dewey Decimal, lcc = Library of Congress. Used for category suggestions.
    ddc: z.array(z.string()).optional(),
    lcc: z.array(z.string()).optional(),
    subject_facet: z.array(z.string()).optional(),
    ol_work_key: z.string().optional(),
    // First-edition anchored fields (populated by scripts/enrich-ol-firstedition.py — see epic #124).
    // first_published refers to the WORK's earliest known publication year.
    // The original_* fields capture the work's original-language publication
    // metadata, distinct from the representative edition we link to (which
    // may be a modern English reprint).
    original_title: z.string().optional(),
    original_language: z.string().optional(),         // ISO 639-3 code
    original_publisher: z.string().optional(),
    original_pages: z.number().optional(),
    first_edition_isbn: z.string().nullable().optional(),  // explicit null for pre-ISBN works
    first_published_circa: z.boolean().optional(),    // for "ca. 1850" / "[1900?]"
    translator: z.string().optional(),                // when original_language differs from language
    editions_count: z.number().optional(),
    // Representative-edition anchored fields. The edition we link to via isbn/pages.
    representative_edition_key: z.string().optional(),  // OL /books/OL...M
    // Wikidata enrichment (populated by scripts/enrich-wikidata-book.py — Epic B in #124)
    wikidata_qid: z.string().optional(),  // Q12345
    awards: z.array(z.object({
      name: z.string(),
      year: z.number().optional(),
    })).optional(),
    series: z.object({
      name: z.string(),
      position: z.number().optional(),
      total: z.number().optional(),
    }).optional(),
    adaptations: z.array(z.object({
      type: z.enum(['film', 'tv', 'stage', 'radio', 'opera', 'other']),
      title: z.string(),
      year: z.number().optional(),
    })).optional(),
    // Per-field source-of-truth tags for provenance-aware merge.
    // Maps field name → source identifier (e.g. "ol_firstedition_v1", "manual").
    // Records without `_provenance` are treated as legacy/rank 0 and any
    // tagged enricher can correct them. See scripts/json_merge.py.
    _provenance: z.record(z.string(), z.string()).optional(),
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
    // Local photo cache (populated by scripts/cache-photos.py — see #94)
    photo_url_source: z.string().optional(),
    photo_cached_at: z.string().optional(),
    // Open Library author identity (populated by enrich-authors.py)
    ol_author_key: z.string().optional(),
    // Wikidata enrichment (Epic B in #124)
    wikidata_qid: z.string().optional(),
    nationality: z.array(z.string()).optional(),     // ISO 3166-1 alpha-2 codes
    alternate_names: z.array(z.string()).optional(),  // pen names, transliterations
    awards: z.array(z.object({
      name: z.string(),
      year: z.number().optional(),
    })).optional(),
    movements: z.array(z.string()).optional(),       // "Beat Generation", "Modernism", etc.
    viaf_id: z.string().optional(),                  // canonical author cross-reference
    _provenance: z.record(z.string(), z.string()).optional(),
  }),
});

export const collections = { books, authors };
