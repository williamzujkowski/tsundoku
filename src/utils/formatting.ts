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
