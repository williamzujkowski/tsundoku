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
  }),
});

export const collections = { books };
