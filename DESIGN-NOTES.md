# Design Notes — Remarque overhaul of Tsundoku

This document records where this implementation extends the Remarque design
system's vocabulary (REMARQUE.md / AGENT_RULES.md) beyond what it currently
specifies, and why. It is meant to feed the upstream "gallery archetype"
discussion (williamzujkowski/remarque#55) — Remarque's four page archetypes
(Essay, Project Dossier, Notebook, Landing) don't yet have a first-class
answer for a cover-grid / bookshelf catalog site, and this project needed
one immediately. Everything below is a deliberate, documented departure —
not a drift.

## Summary of the base restyle

- Fonts: self-hosted Newsreader (display) / Inter (body+UI) / JetBrains
  Mono (metadata), replacing the CDN-loaded Fraunces + system-ui + SF Mono
  stack. See `src/styles/fonts.css`.
- Palette: `src/styles/tokens-site.css` — Remarque's neutral warm-gray base
  with a custom accent re-derived at hue 35 (a terracotta/oxblood "book
  cloth" tone) instead of the default blue, at the same lightness steps the
  spec's accent recipe prescribes. Passes `npx remarque-audit --palette
  src/styles/tokens-site.css --src src/styles` in both themes.
- Shadows removed sitewide, borders quieted to 1px, hover motion reduced to
  color/border transitions on `--motion-fast`, entrance/stagger-reveal
  animations and the skeleton-loading screen removed, pill-shaped badges
  (priority, status, meta tags) converted to plain mono text.
- Theme convention switched to light-default with dark via
  `@media (prefers-color-scheme: dark)` + `[data-theme]`, matching the
  package's canonical direction (previously this site defaulted dark).

## Invented patterns (beyond the spec's vocabulary)

### 1. The "gallery" archetype (cover-grid pages)

Remarque's archetypes are all fundamentally text/document-shaped (Essay,
Dossier, Notebook, Landing). None of them describes a page whose primary
content unit is a grid of images with a caption — which is the core of this
site (`/browse`, home page's "Must-Reads" strip, category/author book
lists). We treated this as a fifth archetype, informally: **Gallery**.

Rules we applied that a future formal Gallery archetype should probably
codify:

- The container widens beyond `--content-standard` (72rem) to
  `--content-wide` (88rem) — a grid of 2:3 cover thumbnails needs more
  horizontal room than an essay does before it starts feeling cramped.
  `--max-width` is aliased to `--content-wide` in `tokens-site.css` and used
  by `.site-nav` / `.site-main` / `.site-footer`. Prose-bearing sections
  within gallery pages (the about page, book descriptions) still narrow
  back down via `.prose-container` / `.content-reading`.
- Cover images are the ONLY images in the system exempt from the strict
  "content-reading width" cap in the Image Treatment rules — a deliberate
  and, we think, correct exception: cover art *is* the content on this
  site, not illustrative decoration of prose. Everything else about the
  Image Treatment rules still applies: 1px `--color-border`, no drop
  shadow, `--radius-none` (see below on radius), mono captions where
  captions exist (book metadata under a cover).
- Grid item hover is restricted to a border-color shift only
  (`--motion-fast`) — no scale, no lift, no shadow growth. See
  `.book-cover-group:hover .book-cover` and `BookGrid.svelte`'s
  `.book-card:hover` in `src/styles/global.css` / `src/components/BookGrid.svelte`.
- Grid density is left to the content: `repeat(auto-fill, minmax(...))` /
  breakpoint-based column counts, never a fixed card size that fights the
  cover's native 2:3 aspect ratio.

### 2. Radius choice: `--radius-none` as the site's identity, not `--radius-sm`

Remarque permits up to `--radius-md` (8px) but doesn't mandate any rounding.
We chose `--radius-none` (square corners) for structural elements — cards,
cover art, list rows, category tiles, letter tiles — to preserve the
"library card catalog" identity this site already had, and because square
corners read as more *bibliographic* than *app-like*. We *do* use
`--radius-sm` (4px) on form controls (search inputs, `<select>` filters,
the search modal) and on the map tooltip, where a touch of softness aids
scanability without undermining the catalog-drawer feel. This is a
conscious two-radius system, not an oversight — worth codifying as a
"structural vs. interactive-surface" radius split if Gallery becomes
formal.

### 3. Category color-coding as a second, orthogonal color system

REMARQUE.md's Color rules say the accent is used for "exactly two things:
inline links and one interactive element per viewport." This site has a
pre-existing content-taxonomy feature — 30 book categories, each assigned
one of 7 hues (`--pop-blue` / `--pop-green` / `--pop-yellow` / `--pop-orange`
/ `--pop-purple` / `--pop-red` / `--pop-cyan`, plus `--pop-pink` shared with
the sanctioned `--color-accent` role) via the `.cat-*` classes in
`tokens-site.css`. We kept this system, deliberately separate from
`--color-accent`:

- `--color-accent` (the terracotta hue) is the *only* color used for link
  and interactive-hover semantics — every hover/focus rule in the system
  references it, never a `--pop-*` value.
- The 7 `--pop-*` hues are pure content taxonomy: they appear only as a
  category tile's border-accent, a category-scoped `--cat-accent`, or a
  status/priority color (read=green, reading=yellow, want=blue) — never as
  a generic "this is clickable" signal.

This is the single largest intentional deviation from "accent used
sparingly, one hue only." We think it's justified because the categories
are data the reader is meant to scan and recognize at a glance across
thousands of items, which is a different job than "signal interactivity."
A future spec amendment might carve out an explicit "content taxonomy
color" allowance, distinct from the interactive accent, with its own
contrast rules (we held all 7 hues to roughly the same lightness/contrast
discipline as the original site's already-audited pop-art palette, but
they are *not* run through `remarque-audit`'s CHECKS array, which only
inspects the sanctioned `--color-*` names).

### 4. Legacy variable aliasing as a migration technique

Not a design pattern so much as an implementation one, but worth recording
for anyone doing a similar retrofit: `tokens-site.css` defines the entire
prior design system's custom-property names (`--bg`, `--text`,
`--text-muted`, `--border`, `--shadow*`, `--pop-pink`, etc.) as `var()`
aliases pointing at the new Remarque tokens, rather than hunting down every
`var(--old-name)` reference across ~30 Astro pages and 5 Svelte islands.
Because CSS custom properties resolve `var()` chains at used-value time
(not at declaration time), a single alias declared once at `:root` stays
theme-reactive automatically — no per-theme duplication needed for the
aliases themselves (only for the literal `--color-*` values and the
`--pop-*` hues they ultimately point through). This is how the whole site
re-themed without a single template edit to `src/pages/*.astro` beyond the
handful of genuine content fixes listed below.

## Bugs found in `remarque-audit` while integrating

Recorded here in case they help the next consumer or informed a package
fix upstream:

- The audit's brace-aware CSS parser (`scripts/lib/css-tokens.mjs`)
  misidentifies the first rule in a file when that file's `@import`
  statements (which are unparenthesized, semicolon-terminated, brace-less)
  precede it: it concatenates all the leading `@import` text into the
  *prelude* of the first actual block, so a file structured as
  `@import 'a'; @import 'b'; :root { ... }` never registers that `:root`
  block as a light-default block at all. Workaround: keep the audited
  palette file import-free (`src/styles/tokens-site.css` has no
  `@import`s; all imports live in `src/styles/global.css`, which pulls the
  palette file in alongside the token aggregator).
- `isDarkBlock`/`isLightRoot` (same file) require an *exact* string match
  against the rule's full prelude (`:root`, `[data-theme="dark"]`,
  `:root.dark`, etc.) — a prelude like `:root:not([data-theme="light"])`
  or `:root[data-theme="dark"]` (both reasonable, defensive selectors, and
  both used by this site's *previous* design system) do not match any of
  the recognized forms and are silently skipped, which reads as "no
  dark-theme declarations found" even though the CSS is valid and correct
  in a browser. We simplified to the package's own exact convention
  (`[data-theme="dark"]` / `[data-theme="light"]`, no `:root` prefix, no
  `:not()` guards) and rely on source order (the explicit `[data-theme]`
  blocks are positioned after the `@media` block) to get correct
  cascade behavior without needing the guard.
- Three of the site's pre-existing category hues
  (`--pop-green`/`--pop-yellow`/`--pop-orange`, light-theme values) were
  outside the sRGB gamut at their original chroma — carried over unnoticed
  from the prior design system, which had never been run through a gamut
  checker. Reduced chroma slightly (0.13→0.12 green, 0.13→0.11 yellow,
  0.16→0.12 orange) until in-gamut; hue and lightness unchanged, so the
  category-color identity is preserved.

## Consciously left un-restyled / out of scope

- `ShareButton.svelte` — Remarque's Disallowed Patterns list calls out
  "social share buttons in content areas." We kept it: it's existing,
  tested functionality (native `navigator.share` with a clipboard
  fallback) and removing it wasn't part of this task's brief ("read on
  Gutenberg" / "Open Library" / etc. links sit in the same row already).
  Restyled quietly (bordered, no shadow, no lift) rather than removed.
- The emoji glyphs used as inline status/type icons (📖 for "reading",
  📋 for "want", the broken-image-fallback glyphs, search-result type
  icons) were left as-is — they're small semantic/content glyphs, not
  decorative iconography, and swapping them for an SVG icon set was out of
  scope for a token/typography restyle.
- Per-page inline `<style>` blocks outside `src/styles/` (stats.astro's
  map tooltip + world-map fills, index.astro's sparkline) were updated for
  token names and the 13px floor but were not otherwise redesigned beyond
  what the token aliasing gives them for free — they were already quiet
  (color-mix fills, thin borders, no shadow-heavy treatments) and don't
  fall inside the `remarque-audit --src src/styles` scan scope, so they
  were lower priority under time constraints.
