<script lang="ts">
  import { onMount } from 'svelte';

  interface SearchItem {
    t: string; // title
    s: string; // subtitle
    u: string; // url path (relative to base)
    y: string; // type: book | author
    c: string; // cover/photo url
    k?: string; // hidden keyword bag — original_title, series, translator, subject_facet, alt names
  }

  // Device 7 (library card-catalog identity layer): drawer-label voice
  // for the per-result type tag.
  function drawerLabel(type: string): string {
    return type === 'book' ? 'Title card' : 'Author card';
  }

  let { baseUrl = '/' }: { baseUrl?: string } = $props();

  let open = $state(false);
  let query = $state('');
  let activeTab = $state<'all' | 'book' | 'author'>('all');
  let items = $state<SearchItem[]>([]);
  let loaded = $state(false);
  let loadError = $state(false);
  let inputEl = $state<HTMLInputElement | undefined>();
  let modalEl = $state<HTMLDivElement | undefined>();
  let triggerEl: HTMLButtonElement | null = null;
  let activeIndex = $state(-1);

  function trapTab(e: KeyboardEvent) {
    if (e.key !== 'Tab' || !modalEl) return;
    const focusable = modalEl.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    );
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const active = document.activeElement;
    if (e.shiftKey && active === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && active === last) {
      e.preventDefault();
      first.focus();
    }
  }

  let allMatching = $derived.by(() => {
    if (query.trim().length < 2 || !loaded) return [];
    const q = query.trim().toLowerCase();
    return items.filter(
      item =>
        item.t.toLowerCase().includes(q) ||
        item.s.toLowerCase().includes(q) ||
        (item.k !== undefined && item.k.toLowerCase().includes(q))
    );
  });

  let bookCount = $derived(allMatching.filter(i => i.y === 'book').length);
  let authorCount = $derived(allMatching.filter(i => i.y === 'author').length);

  let results = $derived.by(() => {
    const list =
      activeTab === 'all'
        ? allMatching
        : allMatching.filter(item => item.y === activeTab);
    return list.slice(0, 10);
  });

  // Persistent live-region text for screen readers.
  let announcement = $derived.by(() => {
    if (!open || !loaded || query.trim().length < 2) return '';
    const n = results.length;
    if (n === 0) return 'No results';
    return `${n} ${n === 1 ? 'result' : 'results'}`;
  });

  async function loadIndex() {
    if (loaded) return;
    loadError = false;
    try {
      const res = await fetch(`${baseUrl}search-index.json`);
      if (!res.ok) {
        loadError = true;
        return;
      }
      items = await res.json();
      loaded = true;
    } catch {
      loadError = true;
    }
  }

  function toggle(e?: Event) {
    open = !open;
    if (open) {
      triggerEl = (e?.currentTarget as HTMLButtonElement) ?? (document.activeElement as HTMLButtonElement | null);
      query = '';
      activeTab = 'all';
      activeIndex = -1;
      void loadIndex();
      setTimeout(() => inputEl?.focus(), 50);
    }
  }

  function close() {
    open = false;
    query = '';
    activeTab = 'all';
    activeIndex = -1;
    triggerEl?.focus();
  }

  function clearQuery() {
    query = '';
    activeIndex = -1;
    inputEl?.focus();
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'k' && (e.metaKey || e.ctrlKey)) {
      // If no other inline search is capturing it
      e.preventDefault();
      toggle();
    }
    if (e.key === 'Escape' && open) {
      close();
    }
    if (open) trapTab(e);
  }

  function handleResultKeydown(e: KeyboardEvent) {
    if (results.length === 0) {
      if (e.key === 'Enter' && query.trim()) {
        e.preventDefault();
        window.location.href = `${baseUrl}browse/?q=${encodeURIComponent(query.trim())}`;
      }
      return;
    }

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      activeIndex = activeIndex < results.length - 1 ? activeIndex + 1 : 0;
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      activeIndex = activeIndex > 0 ? activeIndex - 1 : results.length - 1;
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (activeIndex >= 0 && results[activeIndex]) {
        window.location.href = `${baseUrl}${results[activeIndex].u}`;
      } else if (query.trim()) {
        window.location.href = `${baseUrl}browse/?q=${encodeURIComponent(query.trim())}`;
      }
    }
  }

  onMount(() => {
    function onOpenSearch() {
      if (!open) {
        toggle();
      }
    }
    window.addEventListener('open-search', onOpenSearch);
    return () => {
      window.removeEventListener('open-search', onOpenSearch);
    };
  });
</script>

<svelte:window onkeydown={handleKeydown} />

<button
  type="button"
  onclick={toggle}
  class="search-toggle"
  aria-label="Search catalog (⌘K)"
  title="Search catalog (⌘K)"
>
  <svg class="search-toggle-icon" fill="none" viewBox="0 0 24 24" stroke-width="1.75" stroke="currentColor" aria-hidden="true">
    <path stroke-linecap="round" stroke-linejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
  </svg>
  <span class="search-toggle-label">Search catalog…</span>
  <kbd class="search-toggle-kbd">⌘K</kbd>
</button>

<!-- Persistent live region for screen-reader announcements -->
<span class="sr-only" aria-live="polite" role="status">{announcement}</span>

{#if open}
  <div
    class="overlay"
    onclick={close}
    role="presentation"
  >
    <div
      class="modal"
      bind:this={modalEl}
      onclick={(e) => e.stopPropagation()}
      role="dialog"
      aria-modal="true"
      aria-label="Search books and authors"
    >
      <div class="modal-search-bar">
        <svg class="modal-search-icon" fill="none" viewBox="0 0 24 24" stroke-width="1.75" stroke="currentColor" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
        </svg>

        <input
          bind:this={inputEl}
          bind:value={query}
          type="search"
          placeholder="Search the card catalog…"
          class="modal-search-input"
          aria-label="Search query"
          aria-controls="search-results"
          aria-activedescendant={activeIndex >= 0 ? `search-result-${activeIndex}` : undefined}
          onkeydown={handleResultKeydown}
          oninput={() => activeIndex = -1}
        />

        {#if query.trim().length > 0}
          <button
            type="button"
            class="modal-btn-clear"
            aria-label="Clear query"
            onclick={clearQuery}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12" />
            </svg>
          </button>
        {/if}

        <kbd class="kbd-hint">ESC</kbd>

        <button
          type="button"
          class="modal-close"
          aria-label="Close search"
          onclick={close}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <!-- Category Filter Tabs -->
      {#if allMatching.length > 0}
        <div class="modal-tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'all'}
            class="tab-btn"
            class:tab-active={activeTab === 'all'}
            onclick={() => { activeTab = 'all'; activeIndex = -1; inputEl?.focus(); }}
          >
            All <span class="tab-badge">{allMatching.length}</span>
          </button>
          {#if bookCount > 0}
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'book'}
              class="tab-btn"
              class:tab-active={activeTab === 'book'}
              onclick={() => { activeTab = 'book'; activeIndex = -1; inputEl?.focus(); }}
            >
              Volumes <span class="tab-badge">{bookCount}</span>
            </button>
          {/if}
          {#if authorCount > 0}
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'author'}
              class="tab-btn"
              class:tab-active={activeTab === 'author'}
              onclick={() => { activeTab = 'author'; activeIndex = -1; inputEl?.focus(); }}
            >
              Authors <span class="tab-badge">{authorCount}</span>
            </button>
          {/if}
        </div>
      {/if}

      <div id="search-results" class="results-list" role="listbox">
        {#if loadError}
          <div class="results-message results-error">
            Failed to load search index.
            <a href="{baseUrl}browse/?q={encodeURIComponent(query)}" class="results-browse-link">
              Search browse catalog directly →
            </a>
          </div>
        {:else if !loaded}
          <div class="results-message">Loading search index…</div>
        {:else if query.trim().length < 2}
          <div class="results-message">Type at least 2 characters to search volumes, authors, and subjects…</div>
        {:else if results.length === 0}
          <div class="results-message results-empty">
            No direct matches for "{query}".
            <a href="{baseUrl}browse/?q={encodeURIComponent(query)}" class="results-browse-link">
              Search all catalog volumes on Browse page →
            </a>
          </div>
        {:else}
          {#each results as item, i}
            <a
              id="search-result-{i}"
              href="{baseUrl}{item.u}"
              class="result-item"
              class:result-active={i === activeIndex}
              role="option"
              aria-selected={i === activeIndex}
              onclick={close}
              onmouseenter={() => activeIndex = i}
            >
              {#if item.c}
                <img src={item.c} alt="" class="result-thumb" loading="lazy" />
              {:else}
                <div class="result-thumb-placeholder" aria-hidden="true">
                  {item.y === 'book' ? '📖' : '👤'}
                </div>
              {/if}
              <div class="result-text">
                <p class="result-title">{item.t}</p>
                <p class="result-subtitle">{item.s}</p>
              </div>
              <span class="result-type">{drawerLabel(item.y)}</span>
            </a>
          {/each}

          {#if allMatching.length > 0}
            <a
              href="{baseUrl}browse/?q={encodeURIComponent(query.trim())}"
              class="result-browse-all"
              onclick={close}
            >
              <span>Explore all {allMatching.length} results on Browse page</span>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" d="M13.5 4.5 21 12m0 0-7.5 7.5M21 12H3" />
              </svg>
            </a>
          {/if}
        {/if}
      </div>

      <div class="modal-footer">
        <div class="keyboard-hints">
          <span><kbd class="kbd">↑↓</kbd> navigate</span>
          <span><kbd class="kbd">↵</kbd> select</span>
          <span><kbd class="kbd">esc</kbd> close</span>
        </div>
        {#if loaded && query.trim().length >= 2}
          <span class="results-count">{allMatching.length} {allMatching.length === 1 ? 'match' : 'matches'}</span>
        {/if}
      </div>
    </div>
  </div>
{/if}

<style>
  /* --- Nav Search Trigger --- */
  .search-toggle {
    min-height: 2.25rem;
    padding: 0.35rem 0.65rem;
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    color: var(--text-muted);
    background: var(--bg-surface);
    border: var(--border-width) solid var(--color-border);
    border-radius: var(--radius-sm, 2px);
    cursor: pointer;
    font-family: var(--font-body);
    font-size: var(--text-meta, 0.8125rem);
    transition: color var(--motion-fast) var(--motion-easing),
                border-color var(--motion-fast) var(--motion-easing),
                background var(--motion-fast) var(--motion-easing);
  }

  .search-toggle:hover {
    color: var(--color-accent);
    border-color: var(--color-border-bold);
    background: var(--bg-elevated);
  }

  .search-toggle-icon {
    width: 1rem;
    height: 1rem;
    flex-shrink: 0;
  }

  .search-toggle-label {
    display: none;
    color: var(--text-dim);
    white-space: nowrap;
  }

  .search-toggle-kbd {
    display: none;
    font-family: var(--font-mono);
    font-size: 0.6875rem;
    background: var(--bg-elevated);
    border: var(--border-width) solid var(--color-border);
    padding: 0.1rem 0.35rem;
    border-radius: var(--radius-sm, 2px);
    color: var(--text-dim);
  }

  @media (min-width: 640px) {
    .search-toggle-label {
      display: inline;
    }
    .search-toggle-kbd {
      display: inline;
    }
  }

  /* --- Overlay --- */
  .overlay {
    position: fixed;
    inset: 0;
    z-index: 60;
    background: var(--color-overlay);
    backdrop-filter: blur(4px);
  }

  /* --- Modal --- */
  .modal {
    max-width: 38rem;
    margin: 10vh auto 0;
    background: var(--bg-elevated);
    border: var(--border-width) solid var(--color-border-bold);
    border-radius: var(--radius-sm, 2px);
    overflow: hidden;
  }

  .modal-search-bar {
    display: flex;
    align-items: center;
    gap: 0.625rem;
    padding: 0.35rem 1rem;
    border-bottom: var(--border-width) solid var(--color-border);
    background: var(--bg-surface);
  }

  .modal-search-icon {
    width: 1.25rem;
    height: 1.25rem;
    color: var(--color-accent);
    flex-shrink: 0;
  }

  .modal-search-input {
    flex: 1;
    min-width: 0;
    background: transparent;
    color: var(--text);
    padding: 0.75rem 0;
    font-size: 1rem;
    font-family: var(--font-body);
    border: none;
    outline: none;
  }

  .modal-search-input::placeholder {
    color: var(--text-dim);
    font-family: var(--font-body);
    font-size: 0.9375rem;
  }

  .modal-btn-clear {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 1.5rem;
    height: 1.5rem;
    background: var(--bg-elevated);
    border: var(--border-width) solid var(--color-border);
    border-radius: var(--radius-sm, 2px);
    color: var(--text-dim);
    cursor: pointer;
    flex-shrink: 0;
    transition: color var(--motion-fast) ease;
  }

  .modal-btn-clear:hover {
    color: var(--color-accent);
  }

  .kbd-hint {
    display: none;
    font-size: 0.75rem;
    color: var(--text-dim);
    background: var(--bg-elevated);
    padding: 0.125rem 0.375rem;
    border: var(--border-width) solid var(--color-border);
    font-family: var(--font-mono);
  }

  @media (min-width: 640px) {
    .kbd-hint {
      display: inline;
    }
  }

  .modal-close {
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    width: 2rem;
    height: 2rem;
    color: var(--text-dim);
    background: none;
    border: none;
    cursor: pointer;
    transition: color var(--motion-fast) ease;
  }

  .modal-close:hover {
    color: var(--text);
  }

  .modal-close svg {
    width: 1.125rem;
    height: 1.125rem;
  }

  /* --- Category Tabs --- */
  .modal-tabs {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.35rem 0.875rem;
    background: var(--bg-surface);
    border-bottom: var(--border-width) solid var(--color-border);
  }

  .tab-btn {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    background: none;
    border: var(--border-width) solid transparent;
    border-radius: var(--radius-sm, 2px);
    color: var(--text-dim);
    font-family: var(--font-mono);
    font-size: 0.75rem;
    padding: 0.2rem 0.5rem;
    cursor: pointer;
    transition: color var(--motion-fast) ease, background var(--motion-fast) ease;
  }

  .tab-btn:hover {
    color: var(--text);
  }

  .tab-btn.tab-active {
    background: var(--bg-elevated);
    border-color: var(--color-border);
    color: var(--color-accent);
    font-weight: 600;
  }

  .tab-badge {
    opacity: 0.75;
    font-size: 0.6875rem;
  }

  /* --- Results list --- */
  .results-list {
    max-height: 52vh;
    overflow-y: auto;
  }

  .results-message {
    padding: 2rem 1rem;
    text-align: center;
    font-size: 0.875rem;
    font-family: var(--font-mono);
    color: var(--text-dim);
  }

  .results-browse-link {
    display: block;
    margin-top: 0.5rem;
    color: var(--color-accent);
    text-decoration: underline;
  }

  .results-error {
    color: var(--color-error);
  }

  .results-empty {
    color: var(--text-dim);
  }

  /* Result Item */
  .result-item {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    min-height: 2.75rem;
    padding: 0.625rem 1rem;
    text-decoration: none;
    color: var(--text);
    border-left: 3px solid transparent;
    border-bottom: var(--border-width) solid var(--color-border);
    background: var(--bg-surface);
    transition: border-color var(--motion-fast) ease, background var(--motion-fast) ease;
  }

  .result-item:hover,
  .result-item.result-active {
    background: var(--bg-elevated);
    border-left-color: var(--color-accent);
    color: var(--text);
  }

  .result-thumb {
    width: 2rem;
    height: 2.75rem;
    object-fit: cover;
    flex-shrink: 0;
    border: var(--border-width) solid var(--color-border);
  }

  .result-thumb-placeholder {
    width: 2rem;
    height: 2.75rem;
    background: var(--bg-elevated);
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-dim);
    font-size: 0.8125rem;
    border: var(--border-width) solid var(--color-border);
  }

  .result-text {
    min-width: 0;
    flex: 1;
  }

  .result-title {
    font-family: var(--font-display, serif);
    font-size: 0.9375rem;
    font-weight: 600;
    color: var(--text);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .result-item:hover .result-title,
  .result-item.result-active .result-title {
    color: var(--color-accent);
  }

  .result-subtitle {
    font-family: var(--font-mono);
    font-size: 0.75rem;
    color: var(--text-dim);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .result-type {
    font-family: var(--font-mono);
    font-size: 0.6875rem;
    color: var(--text-dim);
    letter-spacing: 0.04em;
    text-transform: uppercase;
    background: var(--bg-elevated);
    border: var(--border-width) solid var(--color-border);
    padding: 0.15rem 0.375rem;
    border-radius: var(--radius-sm, 2px);
    flex-shrink: 0;
  }

  .result-browse-all {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem 1rem;
    background: var(--bg-elevated);
    border-top: var(--border-width) solid var(--color-border);
    color: var(--color-accent);
    font-family: var(--font-mono);
    font-size: 0.8125rem;
    font-weight: 600;
    text-decoration: none;
    transition: background var(--motion-fast) ease;
  }

  .result-browse-all:hover {
    background: var(--bg-surface);
    color: var(--text);
  }

  /* --- Modal footer --- */
  .modal-footer {
    padding: 0.5rem 1rem;
    border-top: var(--border-width) solid var(--color-border);
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: var(--bg-surface);
  }

  .keyboard-hints {
    font-family: var(--font-mono);
    font-size: 0.75rem;
    color: var(--text-dim);
    display: flex;
    gap: 1rem;
  }

  .kbd {
    background: var(--bg-elevated);
    padding: 0 0.25rem;
    border: var(--border-width) solid var(--color-border);
    font-family: var(--font-mono);
  }

  .results-count {
    font-family: var(--font-mono);
    font-size: 0.75rem;
    color: var(--text-dim);
  }
</style>
