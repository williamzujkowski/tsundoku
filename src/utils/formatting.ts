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

/**
 * Catalog-card call-number formatter — the SINGLE shared source for the
 * library card-catalog identity layer's Device 1 (catalog-card anatomy)
 * and Device 2 (DDC spine-label chip on cover thumbnails). Per the
 * design-review panel's binding condition: one formatter, unit-tested,
 * strict validation — malformed or missing DDC data must render as
 * omitted, never as raw/partial markup.
 *
 * Only the first DDC value is used (book pages already treat ddc[0] as
 * the primary call number elsewhere — see the Classification section on
 * the book detail page). Accepts either the content collection's
 * `string[]` shape or the browse-data wire format's single-string `dd`
 * field, so BookGrid.svelte (wire data) and the .astro pages (content
 * collection) can share one implementation. Returns null (never an empty
 * string or partial match) for anything that doesn't strictly match a
 * Dewey Decimal number.
 */
const DDC_PATTERN = /^[0-9]{1,3}(\.[0-9]+)?$/;

export function formatCallNumber(ddc: string | string[] | undefined | null): string | null {
  if (!ddc) return null;
  const first = Array.isArray(ddc) ? ddc[0] : ddc;
  if (typeof first !== 'string') return null;
  const trimmed = first.trim();
  if (!DDC_PATTERN.test(trimmed)) return null;
  return trimmed;
}

/**
 * Invert "First Last" to catalog-card "Last, First" order (Device 1 and
 * Device 5's card anatomy). Joint bylines (via parseAuthors) invert each
 * component and join with "; ". Organizational names, already-comma'd
 * names, and single-token names pass through unchanged — there's no
 * surname to invert without guessing wrong.
 */
// Lowercase surname particles that fuse with the following token into one
// surname unit ("Le Guin", "Van Gogh", "de la Cruz") rather than being
// treated as a middle name. Heuristic, not a name database — covers the
// common Western multi-word-surname cases without over-fitting.
const SURNAME_PARTICLES = new Set([
  'de', 'del', 'della', 'der', 'di', 'da', 'van', 'von', 'le', 'la', 'du', 'dos', 'das',
]);

export function invertAuthorName(author: string): string {
  if (!author || author === 'Unknown') return author;

  const invertOne = (name: string): string => {
    if (isOrganizationalAuthorName(name)) return name;
    if (name.includes(',')) return name; // already "Last, First" or similar
    const tokens = name.trim().split(/\s+/);
    if (tokens.length < 2) return name;
    let splitIndex = tokens.length - 1;
    while (splitIndex > 0 && SURNAME_PARTICLES.has(tokens[splitIndex - 1].toLowerCase())) {
      splitIndex--;
    }
    const surname = tokens.slice(splitIndex).join(' ');
    const given = tokens.slice(0, splitIndex).join(' ');
    return `${surname}, ${given}`;
  };

  const { parts, isJoint } = parseAuthors(author);
  if (isJoint) return parts.map(invertOne).join('; ');
  return invertOne(author);
}

/** Reading-status -> catalog stamp (Device 3). Uppercase, boxed, no rotation
 *  (unanimously rejected by the panel — legibility, nondeterministic
 *  rendering, kitsch). Reuses the EXISTING status-badge/status-* semantic
 *  colors — no new tokens. */
export interface StatusStamp {
  label: string;
  className: string;
}

export function statusStamp(status: ReadingStatus | undefined | null): StatusStamp | null {
  if (!status) return null;
  if (status === 'read') return { label: 'READ', className: 'status-read' };
  if (status === 'reading') return { label: 'READING', className: 'status-reading' };
  return { label: 'NOT YET', className: 'status-want' };
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
 * its component author names. Handles `&`, ` and `, ` with `, `/`, and `, `,
 * including mixed bylines like "A, B, and C" or "A, B / Org, Inc." (#198).
 *
 * Two-phase split, applied in order:
 *   1. STRONG separators (`&`, ` and `, ` with `, `/`) always indicate joint
 *      authorship and split unconditionally — single-token parts are kept
 *      (e.g. "Marx & Engels" → ["Marx", "Engels"]).
 *   2. Each strong segment is then comma-sub-split, but ONLY when ≥2 of the
 *      resulting sub-parts have 2+ whitespace tokens. This distinguishes a
 *      real "First Last, First Last" list from "Last, First" catalog notation
 *      ("Smith, John") or single-token last-name lists ("Aho, Lam, Sethi"),
 *      which are left intact. A comma immediately before a corporate suffix
 *      ("World Variety Produce, Inc.") is masked so the org name stays one part.
 *
 * Returns `parts: [originalString]` and `isJoint: false` when no split applies,
 * so callers can iterate `parts` uniformly.
 *
 * Keep in sync with split_authors() in scripts/generate-author-stubs.py.
 */
export interface AuthorParts {
  original: string;
  parts: string[];
  isJoint: boolean;
}

// Strong separators always indicate joint authorship — split unconditionally.
const STRONG_SEPARATORS = /\s*(?:&| and | with |\/)\s*/i;
const COMMA_SEPARATOR = /\s*,\s*/;
// A comma immediately followed by a corporate suffix belongs to an organization
// name ("World Variety Produce, Inc."), not an author separator. Mask it with a
// sentinel (\x00, never present in real names) before splitting so the comma
// splitter ignores it, then restore.
const COMMA_SENTINEL = '\x00';
const ORG_SUFFIX_COMMA = /,(\s*(?:Inc|LLC|Ltd|Corp|Co|GmbH|PLC|LP|LLP)\.?\b)/gi;
// Parenthetical groups, e.g. "(Arabic/Persian)" — separators inside them are
// part of the name, never author boundaries.
const PARENS = /\([^)]*\)/g;
// Lowercase connector words appear in org division names ("Division on Earth and
// Life Studies") but never inside a person's name — used to tell a person from
// an institutional sub-unit.
const CONNECTORS = new Set(['on', 'of', 'the', 'and', 'for', 'in', 'de', 'la']);

/** Heuristic: a comma-part that reads as a personal name (not an org unit). */
function looksLikePerson(part: string): boolean {
  const toks = part.split(/\s+/);
  if (toks.length < 2 || toks.length > 4) return false;
  if (isOrganizationalAuthorName(part)) return false;
  return !toks.some((t) => CONNECTORS.has(t.toLowerCase()));
}

/**
 * True for an organizational byline that should NOT be split into people.
 * Three signals must all hold (#198):
 *   - the byline matches the organizational pattern;
 *   - it has no slash OUTSIDE parentheses — a slash is a deliberate contributor
 *     separator (the cookbook byline "... / World Variety Produce, Inc."), and a
 *     slash inside parens ("Various (Arabic/Persian)") is part of the name;
 *   - fewer than 2 comma-parts look like personal names — so an org PREFIX
 *     followed by real people ("Calm Publications Staff, Kevin Crane, Carolyn
 *     Thomson, Peter Dans") still splits, while a pure institutional byline
 *     ("National Research Council, Division ... and ... Committee ...") stays
 *     one entity.
 */
function isIndivisibleOrg(name: string): boolean {
  if (!isOrganizationalAuthorName(name)) return false;
  if (name.replace(PARENS, '').includes('/')) return false;
  const parts = name.split(COMMA_SEPARATOR).map((p) => p.trim()).filter((p) => p.length > 0);
  const personLike = parts.filter(looksLikePerson).length;
  return personLike < 2;
}

/** Comma-sub-split one strong segment, honoring the 2-token + org-suffix guards. */
function commaSubSplit(segment: string): string[] {
  const masked = segment.replace(ORG_SUFFIX_COMMA, `${COMMA_SENTINEL}$1`);
  const raw = masked
    .split(COMMA_SEPARATOR)
    .map((p) => p.replace(new RegExp(COMMA_SENTINEL, 'g'), ',').trim())
    .filter((p) => p.length > 0);
  const multiToken = raw.filter((p) => p.split(/\s+/).length >= 2);
  // Only treat commas as author separators when there's clear evidence of a
  // "First Last, First Last" list: ≥2 sub-parts carry 2+ tokens. Otherwise the
  // commas belong to a single name (catalog notation, org suffix, initials).
  // Strip a trailing comma left by an upstream strong-separator split
  // ("Aho, Lam, Sethi, and Ullman" → segment "Aho, Lam, Sethi,") — #210.
  return multiToken.length >= 2 ? raw : [segment.trim().replace(/,+\s*$/, '').trim()];
}

export function parseAuthors(name: string): AuthorParts {
  if (isIndivisibleOrg(name)) {
    return { original: name, parts: [name], isJoint: false };
  }
  const strong = name.split(STRONG_SEPARATORS).map((p) => p.trim()).filter((p) => p.length > 0);
  const parts = (strong.length >= 2 ? strong : [name]).flatMap(commaSubSplit);
  if (parts.length >= 2) {
    return { original: name, parts, isJoint: true };
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

/**
 * True when this author record is a joint-name alias (e.g. "Robert Jordan &
 * Brandon Sanderson") AND each component author has its own record. Such
 * aliases are effectively duplicates of their component records — useful for
 * URL back-compat but noise in author listings.
 *
 * Pass `knownAuthorNames` as a Set for O(1) lookup.
 */
export function isJointAlias(name: string, knownAuthorNames: Set<string>): boolean {
  const { isJoint, parts } = parseAuthors(name);
  if (!isJoint) return false;
  return parts.every((p) => knownAuthorNames.has(p));
}

/**
 * Organizational / non-person name patterns. These are corporate, editorial,
 * or committee bylines rather than individual authors:
 *   "BookCaps Study Guides Staff", "World Variety Produce, Inc.",
 *   "Commission on Geosciences", "Committee on Grand Canyon Monitoring",
 *   "Ohio State Board of Commerce", "Various (Arabic ...)".
 * Anchored on whole-word boundaries to avoid catching surnames (e.g. a person
 * named "Board" is unlikely; "Inc"/"Staff"/"Committee" never appear as a real
 * given/family name in this catalog).
 */
const ORG_NAME_PATTERN =
  /(\bInc\.?\b|\bLLC\b|\bLtd\.?\b|\bCorp\.?\b|\bStaff\b|\bCommittee\b|\bCommission\b|\bEditors?\b|\bCouncil\b|\bSociety\b|\bAssociation\b|\bFoundation\b|\bInstitute\b|\bBoard\b|^Various\b|\(Various\))/i;

/**
 * True when an author NAME looks organizational / non-person (committee,
 * corporate byline, editorial staff, "Various ..."), rather than an individual.
 */
export function isOrganizationalAuthorName(name: string): boolean {
  return ORG_NAME_PATTERN.test(name);
}

/**
 * A "suppressed author stub" is an intentionally-empty, non-person record that
 * adds noise to the author index without offering any real content. We hide it
 * from the letter index and the index counts (see #112, path A) — but ONLY when
 * it is BOTH content-empty (no bio AND no photo) AND matches an
 * organizational / joint-alias pattern.
 *
 * A plain person who merely lacks a bio/photo is NOT suppressed: those records
 * still link out (e.g. to Open Library) and represent real authors.
 *
 * `knownAuthorNames` is the set of author-record names, used to confirm a
 * joint-string byline's components have their own pages.
 */
export function isSuppressedAuthorStub(
  author: { name: string; bio?: string; photo_url?: string },
  knownAuthorNames: Set<string>,
): boolean {
  const hasBio = !!(author.bio && author.bio.trim());
  const hasPhoto = !!(author.photo_url && author.photo_url.trim());
  if (hasBio || hasPhoto) return false; // real content → always keep
  if (isOrganizationalAuthorName(author.name)) return true;
  if (isJointAlias(author.name, knownAuthorNames)) return true;
  return false;
}

/**
 * ISO 639-3 language code → human-readable English name.
 * We only enumerate languages that actually appear in the catalog;
 * unknown codes pass through uppercased so the UI is never blank.
 */
const LANGUAGE_NAMES: Record<string, string> = {
  eng: 'English',
  fre: 'French', fra: 'French',
  ger: 'German', deu: 'German',
  spa: 'Spanish',
  ita: 'Italian',
  por: 'Portuguese',
  rus: 'Russian',
  jpn: 'Japanese',
  chi: 'Chinese', zho: 'Chinese',
  kor: 'Korean',
  ara: 'Arabic',
  heb: 'Hebrew',
  lat: 'Latin',
  grc: 'Ancient Greek',
  gre: 'Greek', ell: 'Greek',
  pol: 'Polish',
  swe: 'Swedish',
  nor: 'Norwegian',
  dan: 'Danish',
  fin: 'Finnish',
  dut: 'Dutch', nld: 'Dutch',
  cze: 'Czech', ces: 'Czech',
  hun: 'Hungarian',
  tur: 'Turkish',
  hin: 'Hindi',
  san: 'Sanskrit',
  per: 'Persian', fas: 'Persian',
  vie: 'Vietnamese',
  tha: 'Thai',
  yid: 'Yiddish',
  ice: 'Icelandic', isl: 'Icelandic',
  ron: 'Romanian', rum: 'Romanian',
  ukr: 'Ukrainian',
  cat: 'Catalan',
};

export function languageLabel(code: string | undefined | null): string {
  if (!code) return '';
  const lc = code.toLowerCase();
  return LANGUAGE_NAMES[lc] ?? lc.toUpperCase();
}

/**
 * Format a publication year, accommodating BCE (negative ints) and the
 * `circa` flag for approximate dates.
 */
export function formatYear(year: number | undefined | null, circa?: boolean): string {
  if (year === undefined || year === null) return '';
  const prefix = circa ? 'c. ' : '';
  if (year < 0) return `${prefix}${Math.abs(year)} BCE`;
  return `${prefix}${year}`;
}
