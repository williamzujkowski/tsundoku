/**
 * Shared formatting utilities — single source of truth for
 * priority labels, slug generation, reading status display, etc.
 */

export function toSlug(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '');
}

export function priorityLabel(p: number): string {
  if (p === 1) return 'Must-Read';
  if (p === 2) return 'Recommended';
  return 'Supplementary';
}

export function priorityClass(p: number): string {
  if (p === 1) return 'priority-badge priority-must-read';
  if (p === 2) return 'priority-badge priority-recommended';
  return 'priority-badge priority-supplementary';
}

export function priorityBadgeClass(p: number): string {
  if (p === 1) return 'priority-badge priority-must-read';
  return 'priority-badge priority-supplementary';
}

export type ReadingStatus = 'want' | 'reading' | 'read';

export function statusLabel(status: ReadingStatus): string {
  if (status === 'read') return '✓ Read';
  if (status === 'reading') return '📖 Currently Reading';
  return '📋 Want to Read';
}

export function statusClass(status: ReadingStatus): string {
  if (status === 'read') return 'status-badge status-read';
  if (status === 'reading') return 'status-badge status-reading';
  return 'status-badge status-want';
}

export function pluralize(count: number, singular: string, plural?: string): string {
  return count === 1 ? singular : (plural ?? singular + 's');
}

/**
 * Simple seeded PRNG for deterministic shuffling.
 * Uses a linear congruential generator seeded by day-of-year,
 * so featured sections change daily but are stable within a day.
 */
export function seededShuffle<T>(items: T[], seed?: number): T[] {
  const s = seed ?? dayOfYear();
  const result = [...items];
  let state = s;
  for (let i = result.length - 1; i > 0; i--) {
    state = (state * 1664525 + 1013904223) & 0x7fffffff;
    const j = state % (i + 1);
    [result[i], result[j]] = [result[j], result[i]];
  }
  return result;
}

/**
 * Convert an Open Library cover URL to its small variant for thumbnails.
 * -M.jpg (medium, ~180px) → -S.jpg (small, ~60px)
 */
export function thumbnailUrl(url: string): string {
  if (url.includes('covers.openlibrary.org') && url.includes('-M.jpg')) {
    return url.replace('-M.jpg', '-S.jpg');
  }
  return url;
}

function dayOfYear(): number {
  const now = new Date();
  const start = new Date(now.getFullYear(), 0, 0);
  return Math.floor((now.getTime() - start.getTime()) / 86400000);
}

/**
 * Split a multi-author byline ("Robert Jordan & Brandon Sanderson") into
 * its component author names. Handles `&`, ` and `, ` with `, `, `, `/`.
 *
 * Each part must be at least two whitespace-separated tokens — this avoids
 * splitting initials like "L., M.", or single-name pen names with commas.
 *
 * Returns `parts: [originalString]` and `isJoint: false` when no split applies,
 * so callers can iterate `parts` uniformly.
 */
export interface AuthorParts {
  original: string;
  parts: string[];
  isJoint: boolean;
}

// Strong separators always indicate joint authorship — split unconditionally.
const STRONG_SEPARATORS = /\s*(?:&| and | with |\/)\s*/i;
// Comma is ambiguous: "Smith, John" is "Last, First" notation, not joint authors.
// Only treat comma as a separator when each part has 2+ whitespace-separated tokens.
const COMMA_SEPARATOR = /\s*,\s*/;

export function parseAuthors(name: string): AuthorParts {
  const strong = name.split(STRONG_SEPARATORS).map((p) => p.trim()).filter((p) => p.length > 0);
  if (strong.length >= 2) {
    return { original: name, parts: strong, isJoint: true };
  }
  const commaSplit = name
    .split(COMMA_SEPARATOR)
    .map((p) => p.trim())
    .filter((p) => p.length > 0 && p.split(/\s+/).length >= 2);
  if (commaSplit.length >= 2) {
    return { original: name, parts: commaSplit, isJoint: true };
  }
  return { original: name, parts: [name], isJoint: false };
}

/**
 * True when an author detail page (for `authorName`) should claim the given
 * book. Matches both an exact match against the book's full author string
 * (which includes the existing joint-string records like
 * "Robert Jordan & Brandon Sanderson") and component-name matches (so the
 * "Robert Jordan" page also picks up the same book).
 */
export function authorMatches(bookAuthor: string, authorName: string): boolean {
  if (bookAuthor === authorName) return true;
  return parseAuthors(bookAuthor).parts.includes(authorName);
}
