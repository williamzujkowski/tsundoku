<script lang="ts">
  import { onMount } from 'svelte';
  import { thumbnailUrl, formatCallNumber, invertAuthorName, statusStamp } from '../utils/formatting';

  interface Book {
    title: string;
    author: string;
    category: string;
    priority: number;
    slug: string;
    cover_url?: string;
    first_published?: number;
    reading_status?: 'want' | 'reading' | 'read';
    tags?: string[];
    lcc?: string;
    ddc?: string;
    original_language?: string;
    nationality?: string;
  }

  // Compact wire format from /browse-data.json — keep keys short to shrink payload.
  interface WireBook {
    t: string; a: string; s: string; p: number; cat: string;
    co?: string; y?: number; rs?: 'want' | 'reading' | 'read'; g?: string[]; lc?: string;
    dd?: string; ol?: string; n?: string;
  }

  interface BrowseData {
    books: WireBook[];
    categories: string[];
    tags: string[];
    decades?: number[];
    languages?: string[];
    nationalities?: string[];
  }

  // Display labels for the new facet dropdowns.
  const COUNTRY_NAMES: Record<string, string> = {
    GB: 'British', US: 'American', CA: 'Canadian', AU: 'Australian', NZ: 'New Zealander',
    IE: 'Irish', FR: 'French', DE: 'German', IT: 'Italian', ES: 'Spanish', PT: 'Portuguese',
    NL: 'Dutch', BE: 'Belgian', CH: 'Swiss', AT: 'Austrian', SE: 'Swedish', NO: 'Norwegian',
    DK: 'Danish', FI: 'Finnish', IS: 'Icelandic', RU: 'Russian', PL: 'Polish', CZ: 'Czech',
    HU: 'Hungarian', GR: 'Greek', RO: 'Romanian', BG: 'Bulgarian', HR: 'Croatian',
    RS: 'Serbian', UA: 'Ukrainian', TR: 'Turkish', JP: 'Japanese', CN: 'Chinese',
    KR: 'Korean', IN: 'Indian', IL: 'Israeli', IR: 'Iranian', EG: 'Egyptian',
    ZA: 'South African', NG: 'Nigerian', BR: 'Brazilian', AR: 'Argentine', CL: 'Chilean',
    MX: 'Mexican', CO: 'Colombian', PE: 'Peruvian',
  };
  const LANG_NAMES: Record<string, string> = {
    eng: 'English', fre: 'French', fra: 'French', ger: 'German', deu: 'German',
    spa: 'Spanish', ita: 'Italian', por: 'Portuguese', rus: 'Russian', jpn: 'Japanese',
    chi: 'Chinese', zho: 'Chinese', kor: 'Korean', ara: 'Arabic', heb: 'Hebrew',
    lat: 'Latin', grc: 'Ancient Greek', gre: 'Greek', ell: 'Greek', pol: 'Polish',
    swe: 'Swedish', nor: 'Norwegian', dan: 'Danish', fin: 'Finnish', dut: 'Dutch',
    nld: 'Dutch', cze: 'Czech', ces: 'Czech', hun: 'Hungarian', tur: 'Turkish',
    hin: 'Hindi', san: 'Sanskrit', per: 'Persian', fas: 'Persian',
  };
  function natLabel(c: string): string { return COUNTRY_NAMES[c] ?? c; }
  function langLabel(c: string): string { return LANG_NAMES[c] ?? c.toUpperCase(); }

  let { baseUrl = '/' }: { baseUrl?: string } = $props();

  let books = $state<Book[]>([]);
  let categories = $state<string[]>([]);
  let tags = $state<string[]>([]);
  let decades = $state<number[]>([]);
  let languages = $state<string[]>([]);
  let nationalities = $state<string[]>([]);
  let loaded = $state(false);
  let loadError = $state(false);

  let search = $state('');
  let selectedCategory = $state('');
  let selectedPriority = $state(0);
  let selectedStatus = $state('');
  let selectedTag = $state('');
  let selectedDecade = $state(-1); // -1 = any
  let selectedLanguage = $state(''); // original_language
  let selectedNationality = $state(''); // author primary nationality
  let showCount = $state(100);

  onMount(async () => {
    try {
      const res = await fetch(`${baseUrl}browse-data.json`);
      if (!res.ok) { loadError = true; return; }
      const data: BrowseData = await res.json();
      books = data.books.map(b => ({
        title: b.t,
        author: b.a,
        category: b.cat,
        priority: b.p,
        slug: b.s,
        cover_url: b.co,
        first_published: b.y,
        reading_status: b.rs,
        tags: b.g,
        lcc: b.lc,
        ddc: b.dd,
        original_language: b.ol,
        nationality: b.n,
      }));
      categories = data.categories;
      tags = data.tags;
      decades = data.decades ?? [];
      languages = data.languages ?? [];
      nationalities = data.nationalities ?? [];
      loaded = true;
    } catch {
      loadError = true;
    }
  });

  let filtered = $derived(
    books.filter(b => {
      const q = search.toLowerCase();
      const matchesSearch = q === '' ||
        b.title.toLowerCase().includes(q) ||
        b.author.toLowerCase().includes(q);
      const matchesCategory = selectedCategory === '' || b.category === selectedCategory;
      const matchesPriority = selectedPriority === 0 || b.priority === selectedPriority;
      const matchesStatus = selectedStatus === '' || b.reading_status === selectedStatus;
      const matchesTag = selectedTag === '' || (b.tags && b.tags.includes(selectedTag));
      const matchesDecade = selectedDecade === -1
        || (b.first_published !== undefined && Math.floor(b.first_published / 10) * 10 === selectedDecade);
      const matchesLanguage = selectedLanguage === '' || b.original_language === selectedLanguage;
      const matchesNationality = selectedNationality === '' || b.nationality === selectedNationality;
      return matchesSearch && matchesCategory && matchesPriority && matchesStatus
        && matchesTag && matchesDecade && matchesLanguage && matchesNationality;
    })
  );

  let sortedBooks = $derived([...filtered].sort((a, b) => a.title.localeCompare(b.title)));

  function priorityLabel(p: number): string {
    if (p === 1) return 'Must-Read';
    if (p === 2) return 'Recommended';
    return 'Supplementary';
  }

  function priorityClass(p: number): string {
    if (p === 1) return 'priority-badge priority-must-read';
    if (p === 2) return 'priority-badge priority-recommended';
    return 'priority-badge priority-supplementary';
  }

  function clearFilters() {
    search = '';
    selectedCategory = '';
    selectedPriority = 0;
    selectedStatus = '';
    selectedTag = '';
    selectedDecade = -1;
    selectedLanguage = '';
    selectedNationality = '';
  }

  function loadMore() {
    showCount += 100;
  }
</script>

<div class="book-grid-wrapper">
  <!-- Search and filters -->
  <div class="filters-bar">
    <div class="search-wrapper">
      <input
        type="search"
        placeholder="Search books or authors..."
        bind:value={search}
        aria-label="Search books by title or author"
        class="search-input"
      />
      <svg class="search-icon" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
      </svg>
    </div>
    <div class="filter-selects">
      <select bind:value={selectedCategory}
        aria-label="Filter by category"
        class="filter-select">
        <option value="">All Categories</option>
        {#each categories as cat}
          <option value={cat}>{cat}</option>
        {/each}
      </select>
      <select bind:value={selectedPriority}
        aria-label="Filter by priority"
        class="filter-select">
        <option value={0}>All Priorities</option>
        <option value={1}>Must-Read</option>
        <option value={2}>Recommended</option>
        <option value={3}>Supplementary</option>
      </select>
      <select bind:value={selectedStatus}
        aria-label="Filter by reading status"
        class="filter-select">
        <option value="">All Status</option>
        <option value="read">✓ Read</option>
        <option value="reading">📖 Reading</option>
        <option value="want">📋 Want to Read</option>
      </select>
      {#if tags.length > 0}
        <select bind:value={selectedTag}
          aria-label="Filter by genre tag"
          class="filter-select">
          <option value="">All Genres</option>
          {#each tags as tag}
            <option value={tag}>{tag}</option>
          {/each}
        </select>
      {/if}
      {#if decades.length > 0}
        <select bind:value={selectedDecade}
          aria-label="Filter by decade"
          class="filter-select">
          <option value={-1}>All Decades</option>
          {#each decades as d}
            <option value={d}>{d < 0 ? `${Math.abs(d)}s BCE` : `${d}s`}</option>
          {/each}
        </select>
      {/if}
      {#if nationalities.length > 0}
        <select bind:value={selectedNationality}
          aria-label="Filter by author nationality"
          class="filter-select">
          <option value="">All Nationalities</option>
          {#each nationalities as code}
            <option value={code}>{natLabel(code)}</option>
          {/each}
        </select>
      {/if}
      {#if languages.length > 0}
        <select bind:value={selectedLanguage}
          aria-label="Filter by original language"
          class="filter-select">
          <option value="">All Languages</option>
          {#each languages as code}
            <option value={code}>{langLabel(code)}</option>
          {/each}
        </select>
      {/if}
    </div>
  </div>

  <!-- Results bar -->
  <div class="results-bar">
    <p class="results-count" aria-live="polite" aria-atomic="true">
      {#if !loaded && !loadError}
        Loading…
      {:else if sortedBooks.length === books.length}
        {books.length.toLocaleString()} books
      {:else}
        {sortedBooks.length.toLocaleString()} of {books.length.toLocaleString()} books
      {/if}
    </p>
    {#if search !== '' || selectedCategory !== '' || selectedPriority !== 0 || selectedStatus !== '' || selectedTag !== '' || selectedDecade !== -1 || selectedLanguage !== '' || selectedNationality !== ''}
      <button onclick={clearFilters} class="clear-filters-link">
        Clear filters
      </button>
    {/if}
  </div>

  {#if loadError}
    <div class="empty-state">
      <p class="empty-title">Couldn't load the book list</p>
      <p class="empty-subtitle">Something went wrong loading <code>browse-data.json</code>. Try refreshing.</p>
    </div>
  {:else if !loaded}
    <!-- Loading state — plain text, no skeleton screen (Remarque disallows
         skeleton loading animations; "use a simple spinner or nothing"). -->
    <p class="loading-message" role="status">Loading books…</p>
  {:else if sortedBooks.length === 0}
    <!-- Empty state -->
    <div class="empty-state">
      <p class="empty-title">No books found</p>
      <p class="empty-subtitle">Try adjusting your search or filters.</p>
      <button onclick={clearFilters} class="btn-clear-all">
        Clear all filters
      </button>
    </div>
  {:else}
    <!-- Book grid -->
    <div class="book-cards-grid">
      {#each sortedBooks.slice(0, showCount) as book (book.slug)}
        <a href="{baseUrl}books/{book.slug}/" class="book-card">
          <div class="book-card-inner">
            <!-- Device 2 (library card-catalog identity layer): a small
                 mono spine-label chip, bottom-left of the cover, echoing
                 the same real DDC call number the catalog-card anatomy
                 shows in text below — aria-hidden since it's a decorative
                 duplicate, not a second source of information. Built on
                 the SAME formatCallNumber() as Device 1 (panel condition:
                 one shared formatter for both devices). -->
            <div class="book-cover-wrap">
              {#if book.cover_url}
                <img src={thumbnailUrl(book.cover_url)} alt="" width="48" height="72" class="book-thumb" loading="lazy" style:view-transition-name={`cover-${book.slug}`} />
              {:else}
                <div class="book-thumb-placeholder" aria-hidden="true">📖</div>
              {/if}
              {#if formatCallNumber(book.ddc)}
                <span class="cover-spine-chip" aria-hidden="true">{formatCallNumber(book.ddc)}</span>
              {/if}
            </div>
            <!-- Catalog-card anatomy (library card-catalog identity layer,
                 Device 1): mono DDC call number top-left (real data —
                 formatCallNumber validates strictly, omits if missing/
                 malformed, never renders raw markup), surname-first author
                 line, serif title, hairline rules aligned to the text
                 baselines they carry — evoking printed card stock rather
                 than floating as decoration. -->
            <div class="book-info catalog-card-body">
              <div class="catalog-card-row">
                {#if formatCallNumber(book.ddc)}
                  <span class="catalog-call-number">{formatCallNumber(book.ddc)}</span>
                {/if}
                <span class="catalog-card-row-right">
                  <span class={priorityClass(book.priority)}>
                    {priorityLabel(book.priority)}
                  </span>
                  {#if book.first_published}
                    <span class="book-year">{book.first_published}</span>
                  {/if}
                </span>
              </div>
              <div class="catalog-rule" aria-hidden="true"></div>
              <p class="catalog-author">{invertAuthorName(book.author)}</p>
              <h3 class="catalog-title">{book.title}</h3>
              <div class="catalog-rule" aria-hidden="true"></div>
              <div class="book-footer">
                <p class="book-category">{book.category}</p>
                {#if statusStamp(book.reading_status)}
                  {@const stamp = statusStamp(book.reading_status)}
                  {#if stamp}
                    <span class={`status-stamp ${stamp.className}`}>{stamp.label}</span>
                  {/if}
                {/if}
              </div>
            </div>
          </div>
        </a>
      {/each}
    </div>

    <!-- Load more -->
    {#if sortedBooks.length > showCount}
      <div class="load-more-wrapper">
        <button onclick={loadMore} class="btn-load-more">
          Show more ({Math.min(100, sortedBooks.length - showCount)} remaining)
        </button>
      </div>
    {/if}
  {/if}
</div>

<style>
  .book-grid-wrapper {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  @media (min-width: 640px) {
    .book-grid-wrapper {
      gap: 1.5rem;
    }
  }

  /* --- Filters --- */
  .filters-bar {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  /* search-wrapper is now always full-width above the wrapping filters
     row — it's the most-used input and deserves to be the first thing.
     The dropdowns wrap below into as many rows as needed. */
  .search-wrapper { position: relative; }

  .search-input {
    width: 100%;
    min-height: 2.75rem;
    background: var(--bg-surface);
    border: var(--border-width) solid var(--border-strong);
    border-radius: var(--radius-sm);
    color: var(--text);
    padding: 0.625rem 1rem 0.625rem 2.5rem;
    font-size: 1rem;
    font-family: var(--font-body);
  }

  .search-input:focus {
    outline: none;
    border-color: var(--color-accent);
  }

  .search-icon {
    position: absolute;
    left: 0.75rem;
    top: 50%;
    transform: translateY(-50%);
    width: 1rem;
    height: 1rem;
    color: var(--text-dim);
  }

  .filter-selects {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  .filter-select {
    flex: 1 1 8rem;
    min-width: 8rem;
    min-height: 2.75rem;
    background: var(--bg-surface);
    border: var(--border-width) solid var(--border-strong);
    border-radius: var(--radius-sm);
    color: var(--text);
    padding: 0.5rem 0.625rem;
    font-size: 0.9375rem;
    font-family: var(--font-body);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  @media (min-width: 640px) {
    .filter-select {
      flex: 0 1 9rem;
    }
  }

  .filter-select:focus {
    outline: none;
    border-color: var(--color-accent);
  }

  /* --- Results bar --- */
  .results-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .results-count {
    font-size: 0.875rem;
    font-family: var(--font-mono);
    font-weight: 700;
    color: var(--text-muted);
  }

  .clear-filters-link {
    display: inline-flex;
    align-items: center;
    min-height: 2.75rem;
    font-family: var(--font-mono);
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--color-accent);
    background: none;
    border: none;
    text-decoration: underline;
    text-underline-offset: 2px;
    padding-inline: 0.25rem;
    cursor: pointer;
    transition: color 120ms ease;
  }

  .clear-filters-link:hover {
    color: var(--text);
  }

  /* --- Empty state --- */
  .empty-state {
    border: var(--border-width) solid var(--border);
    background: var(--bg-surface);
    padding: 2rem;
    text-align: center;
  }

  @media (min-width: 640px) {
    .empty-state {
      padding: 3rem;
    }
  }

  .empty-title {
    color: var(--text-muted);
    font-size: 1.125rem;
    margin-bottom: 0.5rem;
  }

  .empty-subtitle {
    color: var(--text-dim);
    font-size: 0.875rem;
    margin-bottom: 1rem;
  }

  .btn-clear-all {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 2.75rem;
    background: transparent;
    color: var(--text);
    font-weight: 500;
    padding: 0.625rem 1.5rem;
    font-size: 0.9375rem;
    border: var(--border-width) solid var(--border-strong);
    border-radius: var(--radius-sm);
    cursor: pointer;
    font-family: var(--font-body);
    transition: border-color 120ms ease, color 120ms ease;
  }

  .btn-clear-all:hover {
    border-color: var(--color-accent);
    color: var(--color-accent);
  }

  /* --- Book card grid --- */
  .book-cards-grid {
    display: grid;
    grid-template-columns: 1fr;
    gap: 0.75rem;
  }

  @media (min-width: 640px) {
    .book-cards-grid {
      /* See note in src/styles/global.css — minmax(0, 1fr) prevents long
       * unbreakable titles/authors from blowing out a column. */
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }

  @media (min-width: 1024px) {
    .book-cards-grid {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }
  }

  @media (min-width: 1280px) {
    .book-cards-grid {
      grid-template-columns: repeat(4, minmax(0, 1fr));
    }
  }

  /* --- Book card --- */
  .book-card {
    display: block;
    border: var(--border-width) solid var(--border);
    background: var(--bg-surface);
    padding: 0.75rem;
    text-decoration: none;
    color: var(--text);
    transition: border-color 120ms ease;
  }

  .book-card:hover {
    border-color: var(--color-accent);
    color: var(--text);
  }

  .loading-message {
    font-family: var(--font-mono);
    font-size: 0.9375rem;
    color: var(--text-dim);
    padding: 2rem 0;
    text-align: center;
  }

  .book-card-inner {
    display: flex;
    gap: 0.75rem;
  }

  .book-cover-wrap {
    position: relative;
    flex-shrink: 0;
  }

  .book-thumb {
    width: 3rem;
    height: 4.5rem;
    object-fit: cover;
    flex-shrink: 0;
    border: var(--border-width) solid var(--border);
  }

  .book-card:hover .book-thumb {
    border-color: var(--color-accent);
  }

  /* Device 2: spine-label chip, existing tokens only. Card-stock
     background + top/right hairline only, so it reads as a sticker
     affixed to the cover's own bottom-left corner rather than a floating
     badge — the cover's own edges already close off the other two sides. */
  .cover-spine-chip {
    position: absolute;
    left: 0;
    bottom: 0;
    padding: 0.0625rem 0.25rem;
    background: var(--bg-surface);
    border-top: var(--border-width) solid var(--border);
    border-right: var(--border-width) solid var(--border);
    font-family: var(--font-mono);
    font-size: var(--text-micro);
    line-height: 1.2;
    color: var(--text-dim);
    font-variant-numeric: tabular-nums lining-nums;
    pointer-events: none;
  }

  .book-thumb-placeholder {
    width: 3rem;
    height: 4.5rem;
    flex-shrink: 0;
    background: var(--bg-elevated);
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-dim);
    font-size: 1.125rem;
    border: var(--border-width) solid var(--border);
  }

  .book-info {
    min-width: 0;
    flex: 1;
  }

  /* Catalog-card anatomy (Device 1). Text-only rhythm modeled on a
     printed library catalog card: a mono classification row, a hairline
     rule, the surname-first author line, the serif title, a second
     hairline rule, then the existing footer row. Rules sit directly under
     the text they close off (margin, not padding, on each side) so they
     read as ruled card stock, not a floating decoration. */
  .catalog-card-body {
    display: flex;
    flex-direction: column;
  }

  .catalog-card-row {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 0.5rem;
  }

  .catalog-card-row-right {
    display: flex;
    align-items: baseline;
    gap: 0.375rem;
    flex-shrink: 0;
  }

  .catalog-call-number {
    font-family: var(--font-mono);
    font-size: 0.8125rem;
    color: var(--text-dim);
    font-variant-numeric: tabular-nums lining-nums;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .book-year {
    font-family: var(--font-mono);
    font-size: 0.8125rem;
    color: var(--text-dim);
  }

  .catalog-rule {
    border-top: var(--border-width) solid var(--border);
    margin-block: 0.375rem;
  }

  .catalog-author {
    font-family: var(--font-mono);
    font-size: 0.8125rem;
    letter-spacing: 0.02em;
    color: var(--text-dim);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .catalog-title {
    font-family: var(--font-display);
    font-weight: var(--weight-display, var(--weight-regular));
    color: var(--text);
    font-size: 1rem;
    line-height: 1.25;
    margin-top: 0.125rem;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .book-card:hover .catalog-title {
    color: var(--color-accent);
  }

  .book-footer {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    margin-top: 0.125rem;
  }

  .book-category {
    font-family: var(--font-mono);
    font-size: 0.8125rem;
    color: var(--text-dim);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /* Device 3 (library card-catalog identity layer): reading-status stamp
     — boxed mono uppercase, axis-aligned. No rotation: unanimously
     rejected by the design-review panel (legibility, nondeterministic
     rendering across engines, kitsch). Color comes from the EXISTING
     .status-read/.status-reading/.status-want classes (defined globally,
     already the site's semantic status colors) via currentColor — no new
     color tokens, the border simply follows whichever text color the
     shared class sets. */
  .status-stamp {
    display: inline-flex;
    align-items: center;
    flex-shrink: 0;
    padding: 0.0625rem 0.375rem;
    font-family: var(--font-mono);
    font-size: var(--text-micro);
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    border: var(--border-width) solid currentColor;
    line-height: 1.3;
  }

  /* --- Load more --- */
  .load-more-wrapper {
    text-align: center;
    padding-top: 1rem;
  }

  .btn-load-more {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 2.75rem;
    border: var(--border-width) solid var(--border-strong);
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--text-muted);
    font-weight: 500;
    padding: 0.625rem 1.5rem;
    font-size: 0.9375rem;
    cursor: pointer;
    font-family: var(--font-body);
    transition: border-color 120ms ease, color 120ms ease;
  }

  .btn-load-more:hover {
    border-color: var(--color-accent);
    color: var(--color-accent);
  }
</style>
