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
