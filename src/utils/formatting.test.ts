import { describe, it, expect } from 'vitest';
import {
  toSlug,
  priorityLabel,
  priorityClass,
  priorityBadgeClass,
  statusLabel,
  statusClass,
  statusColor,
  statusIcon,
  pluralize,
  seededShuffle,
  thumbnailUrl,
} from './formatting.js';

describe('toSlug', () => {
  it('lowercases and replaces non-alphanumeric with hyphens', () => {
    expect(toSlug('Computer Science')).toBe('computer-science');
  });

  it('strips leading and trailing hyphens', () => {
    expect(toSlug('--hello--')).toBe('hello');
  });

  it('collapses multiple separators into one hyphen', () => {
    expect(toSlug('AI & Machine Learning')).toBe('ai-machine-learning');
  });

  it('handles already slugified text', () => {
    expect(toSlug('already-a-slug')).toBe('already-a-slug');
  });

  it('handles empty string', () => {
    expect(toSlug('')).toBe('');
  });

  it('handles special characters', () => {
    expect(toSlug("Philosophy & Ethics (Western)")).toBe('philosophy-ethics-western');
  });
});

describe('priorityLabel', () => {
  it('returns Must-Read for priority 1', () => {
    expect(priorityLabel(1)).toBe('Must-Read');
  });

  it('returns Recommended for priority 2', () => {
    expect(priorityLabel(2)).toBe('Recommended');
  });

  it('returns Supplementary for priority 3', () => {
    expect(priorityLabel(3)).toBe('Supplementary');
  });

  it('defaults to Supplementary for unknown priorities', () => {
    expect(priorityLabel(0)).toBe('Supplementary');
    expect(priorityLabel(99)).toBe('Supplementary');
  });
});

describe('priorityClass', () => {
  it('returns purple classes for priority 1', () => {
    expect(priorityClass(1)).toContain('purple');
  });

  it('returns gray classes for priority 2', () => {
    expect(priorityClass(2)).toContain('gray');
  });

  it('returns dim gray classes for priority 3', () => {
    expect(priorityClass(3)).toContain('gray');
  });
});

describe('priorityBadgeClass', () => {
  it('returns purple for priority 1', () => {
    expect(priorityBadgeClass(1)).toContain('purple');
  });

  it('returns gray for other priorities', () => {
    expect(priorityBadgeClass(2)).toContain('gray');
    expect(priorityBadgeClass(3)).toContain('gray');
  });
});

describe('statusLabel', () => {
  it('returns correct labels for each status', () => {
    expect(statusLabel('read')).toBe('✓ Read');
    expect(statusLabel('reading')).toBe('📖 Currently Reading');
    expect(statusLabel('want')).toBe('📋 Want to Read');
  });
});

describe('statusClass', () => {
  it('returns green for read', () => {
    expect(statusClass('read')).toContain('green');
  });

  it('returns amber for reading', () => {
    expect(statusClass('reading')).toContain('amber');
  });

  it('returns blue for want', () => {
    expect(statusClass('want')).toContain('blue');
  });
});

describe('statusColor', () => {
  it('maps status to text color', () => {
    expect(statusColor('read')).toBe('text-green-500');
    expect(statusColor('reading')).toBe('text-amber-500');
    expect(statusColor('want')).toBe('text-blue-500');
  });
});

describe('statusIcon', () => {
  it('maps status to icon', () => {
    expect(statusIcon('read')).toBe('✓');
    expect(statusIcon('reading')).toBe('📖');
    expect(statusIcon('want')).toBe('📋');
  });
});

describe('pluralize', () => {
  it('returns singular for count of 1', () => {
    expect(pluralize(1, 'book')).toBe('book');
  });

  it('returns plural for count != 1', () => {
    expect(pluralize(0, 'book')).toBe('books');
    expect(pluralize(5, 'book')).toBe('books');
  });

  it('uses custom plural form when provided', () => {
    expect(pluralize(2, 'category', 'categories')).toBe('categories');
  });
});

describe('thumbnailUrl', () => {
  it('converts Open Library -M.jpg to -S.jpg', () => {
    expect(thumbnailUrl('https://covers.openlibrary.org/b/id/123-M.jpg'))
      .toBe('https://covers.openlibrary.org/b/id/123-S.jpg');
  });

  it('leaves non-Open Library URLs unchanged', () => {
    const url = 'https://books.google.com/books/content?id=abc';
    expect(thumbnailUrl(url)).toBe(url);
  });

  it('leaves -L.jpg URLs unchanged', () => {
    expect(thumbnailUrl('https://covers.openlibrary.org/b/id/123-L.jpg'))
      .toBe('https://covers.openlibrary.org/b/id/123-L.jpg');
  });

  it('handles empty string', () => {
    expect(thumbnailUrl('')).toBe('');
  });
});

describe('seededShuffle', () => {
  const items = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];

  it('returns same length array', () => {
    expect(seededShuffle(items, 42)).toHaveLength(items.length);
  });

  it('contains all original items', () => {
    const result = seededShuffle(items, 42);
    expect(result.sort((a, b) => a - b)).toEqual(items);
  });

  it('is deterministic with same seed', () => {
    const a = seededShuffle(items, 42);
    const b = seededShuffle(items, 42);
    expect(a).toEqual(b);
  });

  it('produces different order with different seeds', () => {
    const a = seededShuffle(items, 1);
    const b = seededShuffle(items, 2);
    expect(a).not.toEqual(b);
  });

  it('does not mutate original array', () => {
    const original = [...items];
    seededShuffle(items, 42);
    expect(items).toEqual(original);
  });

  it('handles empty array', () => {
    expect(seededShuffle([], 42)).toEqual([]);
  });

  it('handles single-element array', () => {
    expect(seededShuffle([1], 42)).toEqual([1]);
  });
});
