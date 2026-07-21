# Design Notes — Remarque overhaul of Tsundoku

This document records where this implementation extends the Remarque design
system's vocabulary (REMARQUE.md / AGENT_RULES.md) beyond what it currently
specifies, and why. It is meant to feed the upstream "gallery archetype"
discussion (williamzujkowski/remarque#55) — Remarque's four page archetypes
(Essay, Project Dossier, Notebook, Landing) don't yet have a first-class
answer for a cover-grid / bookshelf catalog site, and this project needed
one immediately. Everything below is a deliberate, documented departure —
not a drift.

## Library card-catalog identity layer (epic, design-review ratified 3-0, CORE+)

Tracking issue: williamzujkowski/tsundoku#230. Owner's explicit request
("book cards look more like library cards and other touches that make
this feel much more interesting") is the owner-override this identity
layer runs under for card styling specifically — everything else in this
PR still follows Remarque's rules unmodified.

**Rejected by the panel** (data-free skeuomorphism/kitsch, no real data
behind them): a rod hole through the card (pure ornament from the
physical card-drawer metaphor), an ex-libris bookplate (no per-book
ownership/provenance data on this site to hang one on), and rotating the
reading-status stamp a few degrees for a "hand-stamped" look (hurts
legibility, renders nondeterministically across engines/fonts, reads as
kitsch rather than restraint — this device stays crisp and axis-aligned).

Binding panel conditions, applied throughout: existing tokens only (no new
color/shape tokens); Devices 1 and 2 share one call-number formatter
(`formatCallNumber` in `src/utils/formatting.ts`), unit-tested; DDC values
are validated against `^[0-9]{1,3}(\.[0-9]+)?$` and anything malformed or
missing renders as *omitted*, never as raw/partial markup; no `set:html`
anywhere in the card-anatomy code path (Astro's default escaping only);
motion via duration tokens only; 44px targets and heading order intact;
both audit scopes stay green with no new findings.

### Device 1 — Catalog-card anatomy (`BookGrid.svelte`, the `/browse` grid)

Each book card is now modeled on a printed library catalog card:

- **Mono DDC call number, top-left** (`.catalog-call-number`) — real data:
  the catalog has DDC coverage on effectively every book. Built on
  `formatCallNumber(book.ddc)`, which strictly validates the wire value
  against the DDC pattern and returns `null` for anything malformed or
  absent; the template only renders the `<span>` when a value comes back,
  so there is never an empty or garbled call-number box.
- **Author, surname-first** (`.catalog-author`, e.g. "Herbert, Frank") —
  `invertAuthorName()` reuses the existing `parseAuthors()` joint-byline
  splitter (so "Robert Jordan & Brandon Sanderson" becomes "Jordan,
  Robert; Sanderson, Brandon"), skips organizational/already-comma'd
  names, and handles common multi-word surnames via a small particle list
  (de/van/von/le/la/di/da/…) so "Ursula K. Le Guin" inverts to "Le Guin,
  Ursula K." rather than "Guin, Ursula K. Le." This is a heuristic, not a
  name database — documented as a known limitation.
- **Serif title line** (`.catalog-title`) — `--font-display`
  (Newsreader) at `font-weight: var(--weight-display, var(--weight-regular))`,
  the same dark-mode-compensated weight chain as `.heading-xl`.
- **Hairline rules** (`.catalog-rule`, `border-top: 1px solid
  var(--color-border)`) bracket the author/title block above and below,
  positioned with `margin-block` directly against the text they close
  off — they sit at the baselines they carry, not as a floating divider
  mid-card.
- Card stock is unchanged from the base restyle: `--color-surface`
  background, 1px `--color-border`, no `border-radius` (square corners —
  "catalog cards are square-cornered" per the brief, and this was already
  the site's chosen radius identity, see "Radius choice" below).
- The priority badge and publication year moved to the right side of the
  same top row as the call number (`.catalog-card-row-right`) — DDC now
  owns the anatomically-correct top-left position a catalog card's
  classification line occupies.
- The former LCC-based `.book-call-number` line was removed from this
  card (DDC now fills that anatomical role); LCC stays prominent on the
  book detail page (spine label + Classification section, Device 5).

`browse-data.json`'s wire format gained a `dd` field (`scripts/
generate-browse-data.py`) carrying the book's primary DDC value, alongside
a comment pointing back at `formatCallNumber` as the single validating
consumer.

### Device 2 — DDC spine-label chip on cover thumbnails

A small mono chip, bottom-left of each cover thumbnail in the `/browse`
grid (`.cover-spine-chip` in `BookGrid.svelte`), showing the same DDC
value Device 1 shows as text — built from the exact same
`formatCallNumber(book.ddc)` call, per the panel's binding condition that
Devices 1 and 2 share one formatter. It's `aria-hidden="true"`: the real,
accessible copy of the call number is the visible text in the catalog-card
body (Device 1), so the chip is a decorative echo, not a second source of
information a screen reader needs to announce.

Existing tokens only: `--bg-surface` (chip background, matching card
stock), `--color-border` (top + right hairline only — the cover image's
own edges already close off the other two sides, so the chip reads as a
sticker affixed to the corner rather than a floating badge), `--font-mono`,
`--text-micro` (13px, the smallest sanctioned text size), `--text-dim`.
No new color or shape tokens.

### Device 3 — Reading-status stamps

The `/browse` grid's per-card reading-status indicator (previously an
emoji: ✓/📖/📋) is now a boxed mono uppercase "stamp" — `.status-stamp` in
`BookGrid.svelte`, driven by `statusStamp(book.reading_status)`: `read` →
"READ", `reading` → "READING", `want` → "NOT YET". **No rotation** —
unanimously rejected by the panel (hurts legibility, renders
nondeterministically across text-rendering engines, reads as kitsch
rather than restraint). Axis-aligned, crisp, `border: 1px solid
currentColor` combined with the *existing* `.status-read`/
`.status-reading`/`.status-want` classes (already the site's semantic
status colors, unchanged since the base restyle) — the border simply
follows whatever color the shared class sets, so no new color token was
needed to make the stamp's border match its text.

A second, shared (non-Svelte-scoped) copy of `.status-stamp` was added to
`global.css` as part of Device 5 below, since Device 5 also needed the
stamp treatment on a plain Astro page and `BookGrid.svelte`'s Svelte-scoped
copy can't be reused outside that component. The two copies are
intentionally independent (not deduplicated into one shared import) so
either device can be reverted without breaking the other, per the panel's
"independently revertable" condition.

### Device 5 — Checkout-pocket book page

The book-detail page's metadata card (`src/pages/books/[slug].astro`) now
opens with the same catalog-card anatomy as Device 1, at dossier scale:
a mono DDC call number (`.dossier-call-number`, the same shared
`formatCallNumber(book.ddc)`) followed by a hairline rule
(`.dossier-rule`) before the existing category/priority/author-works/
editions grid. The header is omitted entirely when there's no valid call
number — no empty header, no rule with nothing to close off.

The former "library card pocket" reading-status box is now a **date-due
slip** (`.due-slip`) — the classic due-date card glued inside a library
book's back cover: a "DATE DUE" label over a hairline rule, then mono
date rows on dashed hand-ruled dividers. Real data only, and deliberately
**not** a fabricated reading-history log — the data model has no
per-book reading-date log (only a current `reading_status`), so
inventing one would violate "real data only." Instead the slip is built
from whatever real chronological facts a given book actually has:

- `first_published` (+ the `first_published_circa` "c." flag, via the
  existing `formatYear()`)
- Each award with a known year (`book.awards[].year`) — real Wikidata-
  sourced data already shown elsewhere on the page
- Each adaptation with a known year (`book.adaptations[].year`) —
  likewise already-real data (Device page's own "Adaptations" section)
- The current reading status, as a final row using the same
  `statusStamp()`/`.status-stamp` as Device 3

Rows are sorted chronologically so the slip reads top-to-bottom like a
real one. The whole section is omitted when a book has none of the above
(no dated facts and no reading status) — "skip empty sections cleanly."
Verified against a real book (Dune): DDC "813" header, then "First
published 1965 / Nebula Award for Best Novel 1966 / Hugo Award for Best
Novel 1966 / Seiun Award for Best Translated Long Work 1974 / Status:
READ" — every row a real, already-collected fact.

### Device 7 — Card-catalog drawer framing (Cmd-K search)

Typography/labels only, per the panel's explicit constraint — nothing
structural or behavioral changed in `SearchModal.svelte`: `trapTab()`,
`handleKeydown()`, `handleResultKeydown()`, `toggle()`/`close()`, and
every `aria-*` attribute are untouched, so keyboard nav (⌘K to open,
↑/↓ to move, Enter to select, Esc to close, focus trap, focus restore)
behaves identically to before this device.

Two label changes:

- The input's placeholder reads "Search the card catalog…" and is styled
  in mono, uppercase, tracked — via `::placeholder`, which can carry its
  own font/case independent of the *typed* text, so the input stays
  comfortable to type an ordinary query into while still reading as a
  drawer label when empty.
- Each result row's type tag now reads "Title card" / "Author card"
  (`drawerLabel()`, a pure display mapping) instead of the raw "book"/
  "author" value, set uppercase+tracked like a typed library-drawer
  label. The underlying `item.y` value and everything that reads it
  (icon choice, `aria-label`s, filtering) are unchanged — only what's
  displayed changed.

No result-grouping was added (the brief's "AUTHOR CARDS"/"TITLE CARDS"
phrasing suggested literal section headers, but grouping the flat,
relevance-ordered result list by type would be a structural change the
panel explicitly ruled out) — the per-row singular label ("Title card")
delivers the same drawer-catalog voice without touching how results are
ordered or rendered.

Every Remarque site should have one thing a reader remembers it by — spend
all the boldness there, keep everything else disciplined. This site's
signature device is the word **積ん読** itself, set in **tategaki**
(縦書き, vertical writing: columns run top-to-bottom, flowing right to
left, CJK glyphs upright) as a quiet margin mark beside the "積ん読 —
Tsundoku" heading on the About page (`src/pages/about.astro`,
`.tategaki-mark`).

**Why this, and not something else.** The brief offered three directions;
here's the case for picking tategaki over the other two, and why it beats
inventing a fourth:

- *(Rejected) Spine-edge treatment on every cover thumbnail.* This is a
  real, well-observed detail (shelved books show a shadow line at the
  spine) and it's consistent with the site's "cover art is content"
  stance. But it fails the brief's first instruction — "spend **all** the
  boldness in **one** place" — because a spine-edge would necessarily
  apply to every one of the thousands of cover images across the whole
  site. That's not a signature moment, it's a systemic micro-texture; it
  would read as a subtle rendering detail, not a thing anyone points at
  and says "that's the Tsundoku site." It also risks *decorating* rather
  than *encoding* — the darker edge doesn't say anything true that the
  cover image + 1px border doesn't already say.
- *(Rejected) An "unread pile" stack motif on the stats Not-yet count.*
  This is the most literally on-the-nose reading of 積ん読 ("pile up
  unread"), but executing it honestly without inventing new visual
  furniture (a stack of rectangles, a bar-chart-adjacent shape) risks
  becoming exactly the kind of illustrative decoration Remarque's Visual
  Rules warn against ("no decorative gradients," "components exist to
  support content, not embellish it"). A typographic stack built only from
  existing tokens (borders, mono numerals) would be indistinguishable from
  an ordinary stat card — there's no way to make it *distinctly* a stack
  without adding shape/color that isn't already sanctioned.
- *(Chosen) Tategaki.* This is the only one of the three that is
  *literally true* about the content rather than a metaphor for it:
  積ん読 is a real word in a real writing system that traditionally *is*
  set vertically — on book spines, on shop-window kanban signs, in
  vertical-format Japanese books (which is the entire etymological context
  the word describes: books piling up on a shelf). Rendering the site's
  own name in the direction Japanese books are actually labeled is not a
  decoration bolted onto the content; it *is* the content's own script
  doing what it does. It's also the quietest of the three to execute:
  pure typography, one CSS `writing-mode` property, no new visual
  vocabulary, no color beyond `--color-border-bold` (deliberately *not*
  `--color-accent` — this is texture, not the page's one interactive
  element), and it naturally disappears below the width where there's no
  honest margin to put it in (`@media (max-width: 900px)`) rather than
  fighting for space on mobile.

**Implementation notes:**

- `.tsundoku-mark-row` is a real flex layout (mark + prose column), not an
  absolutely-positioned overlay — it can never overlap or clip the prose,
  at any viewport width down to where it's hidden outright.
- The mark is `aria-hidden="true"` (it's a decorative echo of the visible,
  already-accessible `<h2>` text) with `lang="ja"` kept for correctness.
- Color is `--color-border-bold` (the same token used for functional
  borders/`WCAG 1.4.11`), not `--color-accent` — this keeps faith with
  "accent used for exactly two things," now enforced site-wide after the
  dark-mode sweep above.
- Appears exactly once, on one page. No other page gets a tategaki
  treatment — that's the "one signature place" discipline the brief asks
  for, not a pattern to reuse elsewhere.

## remarque-tokens 0.6.0

Bumped from `^0.5.1`. Two things landed for free, both verified:

- **`--weight-display`** (dark-mode display-weight compensation): added to
  `tokens-site.css` in all four theme blocks (light default, dark media
  query, `[data-theme="dark"]`, `[data-theme="light"]`) at 400/500 per the
  package default. `.heading-xl` in `global.css` (the app's only
  `--text-title`-sized heading — the "display tier" per Font Slots) now
  reads `font-weight: var(--weight-display, var(--weight-regular))`,
  matching the core tier's own `.text-title`/`.text-display` convention
  exactly. `.heading-lg`/`.heading-md` (section/subsection sizes) are
  intentionally left alone — the package doesn't apply the compensation
  there either, and thinner hairlines aren't a problem at those sizes.
  Verified in the served dev-mode CSS: `--weight-display: 400`/`500` are
  both present in `tokens-site.css`'s light/dark blocks, and the
  `font-weight:var(--weight-display, var(--weight-regular))` chain is
  present on `.heading-xl`.
- **`.remarque-endmark`**: applied once, at the natural end of the
  About page's narrative content — after the "Stages of Tsundoku" list
  (the page's emotional/narrative closing beat) and before the closing
  divider + "Back to the pile" CTA. About isn't wrapped in
  `.remarque-prose` (it's stat-badge-heavy, not a pure essay), but the
  endmark's CSS doesn't require that wrapper to render, and the fleuron
  reads correctly as "the story part of this page just ended, here's a
  nav link" — the fit the brief asked to confirm before applying it.

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
one of **8 hues, all distinct from `--color-accent`** (`--pop-pink` /
`--pop-blue` / `--pop-green` / `--pop-yellow` / `--pop-orange` /
`--pop-purple` / `--pop-red` / `--pop-cyan`) via the `.cat-*` classes in
`tokens-site.css`. We kept this system, deliberately separate from
`--color-accent`:

- `--color-accent` (the terracotta hue, H35) is the *only* color used for
  link and interactive-hover semantics — every hover/focus/active rule in
  the system references it, never a `--pop-*` value. **This rule was
  violated in the first cut of this restyle and had to be corrected — see
  "Dark-mode sweep" below.**
- The 8 `--pop-*` hues are pure content taxonomy and semantic state, never
  a generic "this is clickable" signal: a category tile's border-accent, a
  category-scoped `--cat-accent`, a status color (`status-read` = green,
  `status-reading` = yellow, `status-want` = blue), a priority-adjacent
  resource-identity color (Gutenberg = green, HathiTrust = blue, LibriVox
  = yellow — matching `.resource-btn-*` everywhere it appears), or a
  `results-error` state (red). None of them encode rank, decorative
  variety, or "look at this."

This is the single largest intentional deviation from "accent used
sparingly, one hue only." We think it's justified because the categories
and statuses are data the reader is meant to scan and recognize at a
glance across thousands of items, which is a different job than "signal
interactivity." A future spec amendment might carve out an explicit
"content taxonomy color" allowance, distinct from the interactive accent,
with its own contrast rules (we held all 8 hues to roughly the same
lightness/contrast discipline as the original site's already-audited
pop-art palette, but they are *not* run through `remarque-audit`'s CHECKS
array, which only inspects the sanctioned `--color-*` names).

### 4. Legacy variable aliasing as a migration technique

Not a design pattern so much as an implementation one, but worth recording
for anyone doing a similar retrofit: `tokens-site.css` defines the entire
prior design system's custom-property names (`--bg`, `--text`,
`--text-muted`, `--border`, `--shadow*`, `--pop-pink`, etc.) as `var()`
aliases pointing at the new Remarque tokens, rather than hunting down every
`var(--old-name)` reference across ~30 Astro pages and 4 Svelte islands.
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

## Owner follow-up: dark-mode / data-viz sweep

The owner reviewed the live dev server and flagged that the restyle was
**not uniform**: light theme looked correct everywhere checked (home,
About, Authors, Stats), but dark theme and the data-viz-heavy `/stats/`
page still showed the legacy neo-brutalist palette — teal/cyan progress
bars, purple decade-histogram bars, a rainbow-cycling rank-number list on
"Most Represented Authors," and a modal backdrop that compounded with the
dark background to read as near-black.

**Root cause, confirmed.** `npx remarque-audit --palette
src/styles/tokens-site.css --src src/styles` (the command wired into CI)
only scans `src/styles/` — it never sees `<style>` blocks inside
`.astro`/`.svelte` files elsewhere in `src/`, and it only flags *syntactic*
violations (hardcoded hex/rgb/oklch) — a `var(--pop-purple)` reference is
syntactically a token reference, so the audit is blind to it being the
*semantically wrong* token. Two categories of bug slipped through on that
basis:

1. **Interactive-state leakage.** `BookGrid.svelte` and `SearchModal.svelte`
   were edited during the initial restyle for shadows/motion/touch-targets,
   but their hover/focus/active states were left referencing
   `var(--pop-pink)` — a literal rose hue (H350) from the *category* color
   system, not `var(--color-accent)` (the terracotta H35 accent). In dark
   mode `--pop-pink`'s value (`oklch(0.74 0.13 350)`) is considerably more
   saturated/different from the accent than in light mode, which is why it
   read as "still the legacy palette" specifically in dark theme. Fixed:
   every non-semantic `--pop-pink` reference in both files now reads
   `var(--color-accent)` (search input/filter-select focus rings, book-card
   hover, load-more/clear-filters hover, search-result active/hover state).
   The genuinely semantic uses (`.status-indicator.status-read` = green,
   `.results-error` = red) were left untouched.
2. **Decorative chart-fill leakage.** `stats.astro`, `index.astro`, and
   `about.astro` had several data-viz elements and decorative card accents
   still hardwired to specific `--pop-*` hues with no semantic meaning —
   a holdover from the old design, where the 8 pop colors were just "the
   accent palette," not a taxonomy system. Fixed:
   - `stats.astro`: the decade-timeline bar fill, the nationality-distribution
     bar fill, the "Book/Author Data Coverage" progress-bar fills, the
     "Publication Era" bar fill, and the "Must-Read" priority-breakdown bar
     all moved from assorted `--pop-*` values to `var(--color-accent)` —
     each is a single-series bar chart, which is exactly the "one accent,
     used sparingly" case, not a taxonomy.
   - `stats.astro`'s "Most Represented Authors" rank list no longer cycles
     through all 8 `--pop-*` hues per rank (`colors[i % colors.length]`) —
     rank position is not a category, so the rainbow was pure decoration.
     Rank numbers are now plain `text-dim`, and the list-item's left-border
     accent falls back to the default `--color-accent` uniformly.
   - `index.astro`'s home-page sparkline: resting bars moved from
     `--pop-purple` to the neutral `--color-border-bold`; the hover state
     (exactly one bar highighted at a time) legitimately keeps a single
     accent color, now `--color-accent` instead of `--pop-cyan`.
   - `about.astro`'s "How It's Built" tech-stack cards and "Stages of
     Tsundoku" list both cycled through 5–6 `--pop-*` hues with no semantic
     mapping (Astro isn't "cyan," Svelte isn't "orange" in any documented
     sense) — both now fall back to the uniform `--color-accent` via
     `.card-accent-top`/`.card-accent-left`'s default. The **"Free
     Reading" cards were left alone** (Gutenberg = green, LibriVox =
     yellow, HathiTrust = blue) — that mapping is a legitimate,
     already-documented resource-identity system matching
     `.resource-btn-gutenberg`/`.resource-btn-librivox`/`.resource-btn-hathitrust`
     everywhere else in the app, not decoration.
   - `SearchModal.svelte`'s full-viewport overlay was `rgba(0, 0, 0, 0.6)`
     — a literal, pure-black, non-tokenized color, which is what compounded
     with the already-dark dark-theme background to read as near-black
     when the modal was open. Replaced with a new `--color-overlay` token
     (`oklch(0.12 0.01 80 / 0.6)`, theme-invariant — a dimming scrim isn't
     a themed surface) in `tokens-site.css`.

**Wider audit, before/after.** `npx remarque-audit --palette
src/styles/tokens-site.css --src src` (whole `src/`, used here only as a
diagnostic — the CI command stays scoped to `src/styles`, see below):
before this sweep, 8 findings; after, 7. The one resolved finding was the
`rgba(0,0,0,0.6)` overlay. **The remaining 7 are not real violations**
(triaged below) — they're two known limitations of the audit's simple
regex scanner, not detectable by the mechanical audit at all, which is why
this sweep had to be done by hand (`grep` + reading every match in
context) rather than by re-running the tool with a wider `--src`:

- 4 false positives: `SearchModal.svelte:140,231` and
  `[slug].astro:439`/`index.astro:105` all trip the hex-color regex on
  GitHub issue references inside **HTML** `<!-- -->` comments (`#203`,
  `#184`, `#124`) — the audit only strips CSS `/* */` comments before
  scanning, not HTML comments, so `#203` reads as a 3-digit hex triplet.
  No color bug; a parser limitation worth reporting upstream.
- 3 flagged-but-sanctioned: `Layout.astro`'s critical inline `<style
  is:inline>` block (the FOUC-prevention CSS that sets `background`/`color`
  before any stylesheet — including the token file itself — has loaded)
  necessarily duplicates literal `oklch()` values matching
  `tokens-site.css`'s `--color-bg`/`--color-fg`. This can't be a `var()`
  reference: at the point this inline `<style>` executes, no external CSS
  (tokens included) has been fetched yet, which is the entire reason it
  exists. Documented here as a **sanctioned exception** — if
  `tokens-site.css`'s bg/fg values ever change, this block must be updated
  to match (there's no way to keep them in sync automatically without
  reintroducing the FOUC this block exists to prevent).

The CI audit step (`.github/workflows/deploy.yml`) intentionally keeps
`--src src/styles`, matching the task brief — a `--src src` run in CI
would perma-fail on the 4 HTML-comment false positives above, and doesn't
belong in a mechanical gate without fixing the audit's comment-stripping
upstream first. The wider sweep is a one-time manual pass, documented here
so it doesn't have to be redone from scratch next time.

**Documented, sanctioned data-viz/decoration exceptions after this sweep:**

- The world-map choropleth (`stats.astro`'s `mapFillRules`, `--map-low` /
  `--map-high`) — a single-hue ramp from `--color-border-bold` to
  `--color-accent`, not a rainbow. Legitimate.
- `.status-indicator`/`.status-badge` (read/reading/want) and
  `.priority-badge` — content-state semantics, not decoration.
- `.resource-btn-*` and the About-page "Free Reading" cards — resource
  source-identity, consistent across the whole site.
- `--color-overlay` (new) — the modal scrim; not a themed surface, so it's
  intentionally *not* split light/dark.
- The 8-hue `.cat-*` category-coding system (section 3 above).

## Owner follow-up: `ShareButton.svelte` removed

The initial version of this PR kept `ShareButton.svelte` — restyled quietly
rather than removed — since Remarque's Disallowed Patterns list calls out
"social share buttons in content areas" and the component was existing,
tested functionality. The owner reviewed this as an open question and
decided to remove it rather than keep the deviation: the component, its
import, and its render in the book-detail page's link row (`[slug].astro`)
have been deleted. The other resource links in that row (Project
Gutenberg, Open Library, Google Books, Goodreads, WorldCat, HathiTrust,
LibriVox) are unaffected. **Tsundoku is now fully conforming on this rule
— there is no remaining share/social-widget deviation from Remarque.**

## Consciously left un-restyled / out of scope

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
