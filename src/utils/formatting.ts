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
  if (p === 1) return 'bg-purple-900/60 text-purple-300 border border-purple-700/30';
  if (p === 2) return 'bg-gray-800 text-gray-400 border border-gray-700';
  return 'bg-gray-800/50 text-gray-500 border border-gray-700/50';
}

export function priorityBadgeClass(p: number): string {
  if (p === 1) return 'bg-purple-900/60 text-purple-300 border border-purple-700/30';
  return 'bg-gray-800 text-gray-500';
}

export type ReadingStatus = 'want' | 'reading' | 'read';

export function statusLabel(status: ReadingStatus): string {
  if (status === 'read') return '✓ Read';
  if (status === 'reading') return '📖 Currently Reading';
  return '📋 Want to Read';
}

export function statusClass(status: ReadingStatus): string {
  if (status === 'read') return 'bg-green-900/40 border-green-700/50 text-green-300';
  if (status === 'reading') return 'bg-amber-900/40 border-amber-700/50 text-amber-300';
  return 'bg-blue-900/40 border-blue-700/50 text-blue-300';
}

export function statusColor(status: ReadingStatus): string {
  if (status === 'read') return 'text-green-500';
  if (status === 'reading') return 'text-amber-500';
  return 'text-blue-500';
}

export function statusIcon(status: ReadingStatus): string {
  if (status === 'read') return '✓';
  if (status === 'reading') return '📖';
  return '📋';
}

export function pluralize(count: number, singular: string, plural?: string): string {
  return count === 1 ? singular : (plural ?? singular + 's');
}
