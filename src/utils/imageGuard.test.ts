import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { resolveImageSrc } from './imageGuard.js';

// Regression coverage for the production 404 on
// /authors/william-shakespeare/ — see imageGuard.ts / scripts/image_guard.py
// docstrings for the full incident writeup.

let publicDir: string;

beforeEach(() => {
  publicDir = mkdtempSync(join(tmpdir(), 'tsundoku-image-guard-'));
  mkdirSync(join(publicDir, 'cached', 'authors'), { recursive: true });
  mkdirSync(join(publicDir, 'cached', 'covers'), { recursive: true });
});

afterEach(() => {
  rmSync(publicDir, { recursive: true, force: true });
});

describe('resolveImageSrc — non-local urls', () => {
  it('returns undefined for undefined', () => {
    expect(resolveImageSrc(undefined, undefined, publicDir)).toBeUndefined();
  });

  it('returns undefined for null', () => {
    expect(resolveImageSrc(null, null, publicDir)).toBeUndefined();
  });

  it('returns undefined for an empty string', () => {
    expect(resolveImageSrc('', undefined, publicDir)).toBeUndefined();
  });

  it('passes a remote url through unchanged', () => {
    const url = 'https://covers.openlibrary.org/b/id/8541860-L.jpg';
    expect(resolveImageSrc(url, undefined, publicDir)).toBe(url);
  });

  it('passes a remote url through even when a source is also given', () => {
    const url = 'https://covers.openlibrary.org/b/id/8541860-L.jpg';
    expect(resolveImageSrc(url, 'https://example.com/other.jpg', publicDir)).toBe(url);
  });
});

describe('resolveImageSrc — local url, file exists', () => {
  it('returns the /tsundoku/cached/ url unchanged when the file is present', () => {
    writeFileSync(join(publicDir, 'cached', 'authors', 'william-shakespeare.jpg'), 'x');
    const url = '/tsundoku/cached/authors/william-shakespeare.jpg';
    expect(resolveImageSrc(url, undefined, publicDir)).toBe(url);
  });

  it('returns the legacy unprefixed /cached/ url unchanged when the file is present', () => {
    writeFileSync(join(publicDir, 'cached', 'covers', 'dune.jpg'), 'x');
    const url = '/cached/covers/dune.jpg';
    expect(resolveImageSrc(url, undefined, publicDir)).toBe(url);
  });
});

describe('resolveImageSrc — local url, file missing', () => {
  it('falls back to sourceUrl when the cached file is missing', () => {
    const url = '/tsundoku/cached/authors/william-shakespeare.jpg';
    const source =
      'https://upload.wikimedia.org/wikipedia/commons/thumb/2/21/William_Shakespeare.jpg';
    expect(resolveImageSrc(url, source, publicDir)).toBe(source);
  });

  it('returns undefined when the file is missing and there is no source', () => {
    const url = '/tsundoku/cached/authors/ghost.jpg';
    expect(resolveImageSrc(url, undefined, publicDir)).toBeUndefined();
  });

  it('returns undefined when source is an empty string', () => {
    const url = '/tsundoku/cached/authors/ghost.jpg';
    expect(resolveImageSrc(url, '', publicDir)).toBeUndefined();
  });

  it('never throws when the cached/ directory does not exist at all', () => {
    const emptyDir = mkdtempSync(join(tmpdir(), 'tsundoku-image-guard-empty-'));
    try {
      const url = '/tsundoku/cached/authors/ghost.jpg';
      expect(resolveImageSrc(url, 'https://example.com/x.jpg', emptyDir)).toBe(
        'https://example.com/x.jpg',
      );
    } finally {
      rmSync(emptyDir, { recursive: true, force: true });
    }
  });
});

describe('resolveImageSrc — real-world regression', () => {
  it('recovers the exact william-shakespeare incident', () => {
    const photoUrl = '/tsundoku/cached/authors/william-shakespeare.jpg';
    const photoUrlSource =
      'https://upload.wikimedia.org/wikipedia/commons/thumb/2/21/' +
      'William_Shakespeare_by_John_Taylor%2C_edited.jpg/400px-' +
      'William_Shakespeare_by_John_Taylor%2C_edited.jpg';
    const resolved = resolveImageSrc(photoUrl, photoUrlSource, publicDir);
    expect(resolved).toBe(photoUrlSource);
    expect(resolved?.startsWith('/tsundoku/cached/')).toBe(false);
  });
});
