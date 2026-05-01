import { describe, it, expect } from 'vitest';
import {
  toSlug,
  priorityLabel,
  priorityClass,
  priorityBadgeClass,
  statusLabel,
  statusClass,
  pluralize,
  seededShuffle,
  thumbnailUrl,
  parseAuthors,
  authorMatches,
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
  it('returns must-read class for priority 1', () => {
    expect(priorityClass(1)).toContain('priority-must-read');
  });

  it('returns recommended class for priority 2', () => {
    expect(priorityClass(2)).toContain('priority-recommended');
  });

  it('returns supplementary class for priority 3', () => {
    expect(priorityClass(3)).toContain('priority-supplementary');
  });
});

describe('priorityBadgeClass', () => {
  it('returns must-read for priority 1', () => {
    expect(priorityBadgeClass(1)).toContain('priority-must-read');
  });

  it('returns supplementary for other priorities', () => {
    expect(priorityBadgeClass(2)).toContain('priority-supplementary');
    expect(priorityBadgeClass(3)).toContain('priority-supplementary');
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
  it('returns read class for read', () => {
    expect(statusClass('read')).toContain('status-read');
  });

  it('returns reading class for reading', () => {
    expect(statusClass('reading')).toContain('status-reading');
  });

  it('returns want class for want', () => {
    expect(statusClass('want')).toContain('status-want');
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

describe('parseAuthors', () => {
  it('returns single part for plain name', () => {
    const r = parseAuthors('Plato');
    expect(r.isJoint).toBe(false);
    expect(r.parts).toEqual(['Plato']);
  });

  it('splits on ampersand', () => {
    const r = parseAuthors('Robert Jordan & Brandon Sanderson');
    expect(r.isJoint).toBe(true);
    expect(r.parts).toEqual(['Robert Jordan', 'Brandon Sanderson']);
  });

  it('splits on " and "', () => {
    const r = parseAuthors('Brian W. Kernighan and Rob Pike');
    expect(r.isJoint).toBe(true);
    expect(r.parts).toEqual(['Brian W. Kernighan', 'Rob Pike']);
  });

  it('splits on comma when each part is multi-word', () => {
    const r = parseAuthors('Niccolò Machiavelli, Stephen Brennan');
    expect(r.isJoint).toBe(true);
    expect(r.parts).toEqual(['Niccolò Machiavelli', 'Stephen Brennan']);
  });

  it('does NOT split when parts would be single-word', () => {
    // Initials with commas like "L., M." should NOT split
    const r = parseAuthors('A.A. Milne');
    expect(r.isJoint).toBe(false);
    expect(r.parts).toEqual(['A.A. Milne']);
  });

  it('preserves the original string', () => {
    expect(parseAuthors('Karl Marx and Friedrich Engels').original).toBe(
      'Karl Marx and Friedrich Engels',
    );
  });

  it('handles three-author entries', () => {
    const r = parseAuthors('Abraham Silberschatz, Peter Galvin, Greg Gagne');
    expect(r.parts.length).toBe(3);
  });

  it('splits single-word last names joined by ampersand', () => {
    const r = parseAuthors('Marx & Engels');
    expect(r.isJoint).toBe(true);
    expect(r.parts).toEqual(['Marx', 'Engels']);
  });

  it('does not split "Last, First" notation', () => {
    // "Smith, John" is library-catalog notation, not two authors.
    const r = parseAuthors('Smith, John');
    expect(r.isJoint).toBe(false);
    expect(r.parts).toEqual(['Smith, John']);
  });
});

describe('authorMatches', () => {
  it('matches exact full string', () => {
    expect(authorMatches('Plato', 'Plato')).toBe(true);
  });

  it('matches the joint string against its own page', () => {
    // The joint-string author detail page (which exists historically) still works.
    expect(
      authorMatches(
        'Robert Jordan & Brandon Sanderson',
        'Robert Jordan & Brandon Sanderson',
      ),
    ).toBe(true);
  });

  it('matches a component name', () => {
    expect(
      authorMatches('Robert Jordan & Brandon Sanderson', 'Robert Jordan'),
    ).toBe(true);
    expect(
      authorMatches('Robert Jordan & Brandon Sanderson', 'Brandon Sanderson'),
    ).toBe(true);
  });

  it('does not match unrelated names', () => {
    expect(authorMatches('Plato', 'Aristotle')).toBe(false);
  });

  it('does not match a substring (e.g. last name)', () => {
    // We want exact part match, not substring.
    expect(authorMatches('Robert Jordan & Brandon Sanderson', 'Jordan')).toBe(false);
  });
});
