/**
 * Build-time guard against emitting a /cached/ image URL whose file
 * doesn't actually exist on disk. TypeScript mirror of
 * scripts/image_guard.py — see that file's docstring for the full
 * incident writeup (production 404 on /authors/william-shakespeare/:
 * the record's JSON claimed a local cached path that was never actually
 * downloaded onto the CI runner building that deploy).
 *
 * Node-only (uses `node:fs`). Import this ONLY from `.astro` frontmatter,
 * which runs exclusively at build time in Node — NEVER from a module
 * shared with a Svelte island (BookGrid.svelte / SearchModal.svelte
 * import `./formatting`, which stays fs-free on purpose so it can be
 * bundled for the browser; those two islands get the same guarantee via
 * the Python generators that produce the JSON they fetch at runtime —
 * see generate-browse-data.py / generate-search-index.py).
 */
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';

const ASTRO_BASE = '/tsundoku/';
const DEFAULT_PUBLIC_DIR = resolve(process.cwd(), 'public');

/**
 * Return a URL that is safe to render right now, or `undefined`.
 *
 * - Falsy `url` -> undefined (caller renders its placeholder).
 * - `url` is not a local `/cached/` path (a plain remote http(s) URL) ->
 *   returned unchanged; nothing to verify.
 * - `url` IS a local `/cached/` path and the file exists on disk in
 *   `publicDir` -> returned unchanged.
 * - `url` IS a local `/cached/` path but the file is MISSING -> falls
 *   back to `sourceUrl` (the original upstream URL, preserved by
 *   cache-photos.py in `cover_url_source` / `cover_url_large_source` /
 *   `photo_url_source`), or `undefined` if there's no source on record.
 *
 * `publicDir` is overridable for tests; production call sites always use
 * the default (the real `public/` directory this repo builds from).
 */
export function resolveImageSrc(
  url: string | undefined | null,
  sourceUrl?: string | null,
  publicDir: string = DEFAULT_PUBLIC_DIR,
): string | undefined {
  if (!url) return undefined;
  if (!(url.startsWith(`${ASTRO_BASE}cached/`) || url.startsWith('/cached/'))) {
    return url;
  }
  // Both "/tsundoku/cached/covers/x.jpg" and "/cached/covers/x.jpg" carry
  // the same suffix after the LAST "cached/" — split on that literal
  // rather than assuming which base prefix is present.
  const parts = url.split('cached/');
  const relative = parts[parts.length - 1] ?? '';
  const fsPath = resolve(publicDir, 'cached', relative);
  if (existsSync(fsPath)) return url;
  return sourceUrl || undefined;
}
