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
  }),
});

export const collections = { books };
