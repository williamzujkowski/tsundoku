<script lang="ts">
  import { onMount } from 'svelte';

  interface SearchItem {
    t: string; // title or author name
    s: string; // subtitle (author — category, or book count)
    u: string; // url path
    y: string; // type: 'book' | 'author'
    c: string; // cover/photo url
    k?: string; // keywords bag
  }

  let {
    baseUrl = '/',
    totalBooks = 3584,
  }: {
    baseUrl?: string;
    totalBooks?: number;
  } = $props();

  let query = $state('');
  let isOpen = $state(false);
  let activeTab = $state<'all' | 'book' | 'author'>('all');
  let activeIndex = $state(-1);
  let items = $state<SearchItem[]>([]);
  let loaded = $state(false);
  let loadError = $state(false);

  let inputEl = $state<HTMLInputElement | undefined>();
  let containerEl = $state<HTMLDivElement | undefined>();

  function drawerLabel(type: string): string {
    return type === 'book' ? 'Title card' : 'Author card';
  }

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

  function handleFocus() {
    void loadIndex();
    if (query.trim().length >= 2) {
      isOpen = true;
    }
  }

  function handleInput() {
    void loadIndex();
    activeIndex = -1;
    if (query.trim().length >= 2) {
      isOpen = true;
    } else {
      isOpen = false;
    }
  }

  function clearQuery() {
    query = '';
    isOpen = false;
    activeIndex = -1;
    inputEl?.focus();
  }

  // Filtered results based on search query and active tab
  let allMatching = $derived.by(() => {
    const q = query.trim().toLowerCase();
    if (q.length < 2 || !loaded) return [];
    return items.filter(
      item =>
        item.t.toLowerCase().includes(q) ||
        item.s.toLowerCase().includes(q) ||
        (item.k !== undefined && item.k.toLowerCase().includes(q))
    );
  });

  let bookCount = $derived(allMatching.filter(i => i.y === 'book').length);
  let authorCount = $derived(allMatching.filter(i => i.y === 'author').length);

  let displayedResults = $derived.by(() => {
    const list =
      activeTab === 'all'
        ? allMatching
        : allMatching.filter(item => item.y === activeTab);
    return list.slice(0, 7);
  });

  function handleSubmit(e: SubmitEvent) {
    e.preventDefault();
    if (activeIndex >= 0 && displayedResults[activeIndex]) {
      window.location.href = `${baseUrl}${displayedResults[activeIndex].u}`;
      return;
    }
    const q = query.trim();
    if (q) {
      window.location.href = `${baseUrl}browse/?q=${encodeURIComponent(q)}`;
    } else {
      window.location.href = `${baseUrl}browse/`;
    }
  }

  function handleKeydown(e: KeyboardEvent) {
    if (!isOpen || displayedResults.length === 0) {
      if (e.key === 'ArrowDown' && query.trim().length >= 2) {
        isOpen = true;
        e.preventDefault();
      }
      return;
    }

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      activeIndex = activeIndex < displayedResults.length - 1 ? activeIndex + 1 : 0;
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      activeIndex = activeIndex > 0 ? activeIndex - 1 : displayedResults.length - 1;
    } else if (e.key === 'Escape') {
      e.preventDefault();
      isOpen = false;
      activeIndex = -1;
    }
  }

  onMount(() => {
    void loadIndex();

    function handleClickOutside(e: MouseEvent) {
      if (containerEl && !containerEl.contains(e.target as Node)) {
        isOpen = false;
      }
    }

    function handleGlobalShortcut(e: KeyboardEvent) {
      if (e.key === 'k' && (e.metaKey || e.ctrlKey)) {
        // If this homepage search bar is on screen, focus it directly
        e.preventDefault();
        inputEl?.focus();
        inputEl?.select();
        void loadIndex();
      }
    }

    document.addEventListener('click', handleClickOutside);
    window.addEventListener('keydown', handleGlobalShortcut);

    return () => {
      document.removeEventListener('click', handleClickOutside);
      window.removeEventListener('keydown', handleGlobalShortcut);
    };
  });
</script>

<div class="catalog-search-container" bind:this={containerEl} onkeydown={handleKeydown}>
  <form
    role="search"
    class="catalog-search-form"
    onsubmit={handleSubmit}
    action="{baseUrl}browse/"
    method="get"
  >
    <div class="search-input-box" class:is-focused={isOpen}>
      <svg
        class="search-icon"
        width="20"
        height="20"
        fill="none"
        viewBox="0 0 24 24"
        stroke-width="1.75"
        stroke="currentColor"
        aria-hidden="true"
      >
        <path
          stroke-linecap="round"
          stroke-linejoin="round"
          d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z"
        />
      </svg>

      <input
        bind:this={inputEl}
        bind:value={query}
        type="search"
        name="q"
        autocomplete="off"
        spellcheck="false"
        placeholder="Search {totalBooks.toLocaleString()} volumes by title, author, subject, or call number…"
        class="catalog-input"
        aria-label="Search the catalog"
        aria-autocomplete="list"
        aria-expanded={isOpen}
        aria-controls="catalog-search-dropdown"
        onfocus={handleFocus}
        oninput={handleInput}
        onkeydown={handleKeydown}
      />

      {#if query.trim().length > 0}
        <button
          type="button"
          class="btn-clear"
          aria-label="Clear search query"
          onclick={clearQuery}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12" />
          </svg>
        </button>
      {:else}
        <kbd class="shortcut-chip" title="Press ⌘K or Ctrl+K to search">⌘K</kbd>
      {/if}

      <button type="submit" class="btn-search-submit" aria-label="Submit search">
        <span>Search</span>
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" d="M13.5 4.5 21 12m0 0-7.5 7.5M21 12H3" />
        </svg>
      </button>
    </div>
  </form>

  <!-- Live Suggestions Dropdown (anchored directly under the input) -->
  {#if isOpen && query.trim().length >= 2}
    <div
      id="catalog-search-dropdown"
      class="catalog-dropdown"
      role="listbox"
      aria-label="Search suggestions"
    >
      <!-- Classification Segment Filters -->
      {#if allMatching.length > 0}
        <div class="dropdown-tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'all'}
            class="tab-btn"
            class:tab-active={activeTab === 'all'}
            onclick={() => { activeTab = 'all'; activeIndex = -1; inputEl?.focus(); }}
          >
            All <span class="tab-count">{allMatching.length}</span>
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
              Volumes <span class="tab-count">{bookCount}</span>
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
              Authors <span class="tab-count">{authorCount}</span>
            </button>
          {/if}
        </div>
      {/if}

      <!-- Results list -->
      <div class="dropdown-body">
        {#if loadError}
          <div class="dropdown-message error-msg">
            Catalog index could not be loaded. Press Enter to search browse catalog.
          </div>
        {:else if !loaded}
          <div class="dropdown-message">Loading library index…</div>
        {:else if displayedResults.length === 0}
          <div class="dropdown-message">
            No direct matches for "{query}".
            <a href="{baseUrl}browse/?q={encodeURIComponent(query)}" class="browse-link">
              Search all catalog volumes on Browse page →
            </a>
          </div>
        {:else}
          {#each displayedResults as item, idx}
            <a
              href="{baseUrl}{item.u}"
              class="suggestion-row"
              class:row-active={idx === activeIndex}
              role="option"
              aria-selected={idx === activeIndex}
              onmouseenter={() => activeIndex = idx}
            >
              <div class="thumb-wrap">
                {#if item.c}
                  <img src={item.c} alt="" class="suggestion-thumb" loading="lazy" />
                {:else}
                  <div class="suggestion-thumb-placeholder" aria-hidden="true">
                    {item.y === 'book' ? '📖' : '👤'}
                  </div>
                {/if}
              </div>

              <div class="suggestion-meta">
                <span class="suggestion-title">{item.t}</span>
                <span class="suggestion-subtitle">{item.s}</span>
              </div>

              <span class="suggestion-tag">{drawerLabel(item.y)}</span>
            </a>
          {/each}
        {/if}
      </div>

      <!-- Action Footer -->
      <div class="dropdown-footer">
        <div class="footer-keyboard-hint">
          <span><kbd class="kbd">↑↓</kbd> Select</span>
          <span><kbd class="kbd">↵</kbd> Open</span>
          <span><kbd class="kbd">esc</kbd> Dismiss</span>
        </div>
        <a href="{baseUrl}browse/?q={encodeURIComponent(query)}" class="view-all-link">
          Explore all results on Browse page →
        </a>
      </div>
    </div>
  {/if}
</div>

<style>
  .catalog-search-container {
    position: relative;
    width: 100%;
    max-width: 44rem;
    margin-inline: auto;
    margin-bottom: var(--space-6);
  }

  .catalog-search-form {
    width: 100%;
  }

  .search-input-box {
    display: flex;
    align-items: center;
    gap: 0.625rem;
    width: 100%;
    min-height: 3.25rem;
    padding: 0.375rem 0.625rem 0.375rem 1rem;
    background: var(--bg-surface);
    border: var(--border-width) solid var(--color-border-bold);
    border-radius: var(--radius-sm, 2px);
    transition: border-color var(--motion-fast) var(--motion-easing),
                background var(--motion-fast) var(--motion-easing);
  }

  .search-input-box:focus-within,
  .search-input-box.is-focused {
    border-color: var(--color-accent);
    background: var(--bg-surface);
    outline: 1px solid var(--color-accent);
  }

  .search-icon {
    flex-shrink: 0;
    color: var(--color-accent);
  }

  .catalog-input {
    flex: 1;
    min-width: 0;
    height: 2.5rem;
    background: transparent;
    border: none;
    outline: none;
    font-family: var(--font-body);
    font-size: 1rem;
    color: var(--text);
  }

  .catalog-input::placeholder {
    color: var(--text-dim);
    font-size: 0.9375rem;
    font-family: var(--font-body);
  }

  .btn-clear {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 1.75rem;
    height: 1.75rem;
    background: var(--bg-elevated);
    border: var(--border-width) solid var(--color-border);
    border-radius: var(--radius-sm, 2px);
    color: var(--text-dim);
    cursor: pointer;
    flex-shrink: 0;
    transition: color var(--motion-fast) ease, border-color var(--motion-fast) ease;
  }

  .btn-clear:hover {
    color: var(--color-accent);
    border-color: var(--color-accent);
  }

  .shortcut-chip {
    display: none;
    font-family: var(--font-mono);
    font-size: 0.75rem;
    font-weight: 500;
    background: var(--bg-elevated);
    border: var(--border-width) solid var(--color-border);
    padding: 0.2rem 0.45rem;
    border-radius: var(--radius-sm, 2px);
    color: var(--text-dim);
    flex-shrink: 0;
  }

  @media (min-width: 640px) {
    .shortcut-chip {
      display: inline-block;
    }
  }

  .btn-search-submit {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    min-height: 2.25rem;
    padding: 0 0.875rem;
    background: var(--bg-elevated);
    border: var(--border-width) solid var(--color-border);
    border-radius: var(--radius-sm, 2px);
    color: var(--text);
    font-family: var(--font-mono);
    font-size: 0.8125rem;
    font-weight: 600;
    cursor: pointer;
    flex-shrink: 0;
    transition: background var(--motion-fast) ease,
                color var(--motion-fast) ease,
                border-color var(--motion-fast) ease;
  }

  .btn-search-submit:hover {
    background: var(--color-accent);
    color: var(--color-bg, #fff);
    border-color: var(--color-accent);
  }

  /* --- Dropdown Results --- */
  .catalog-dropdown {
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    right: 0;
    z-index: 50;
    background: var(--bg-elevated);
    border: var(--border-width) solid var(--color-border-bold);
    border-radius: var(--radius-sm, 2px);
    overflow: hidden;
  }

  /* Segment filter tabs */
  .dropdown-tabs {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.375rem 0.75rem;
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
    padding: 0.25rem 0.5rem;
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

  .tab-count {
    opacity: 0.75;
    font-size: 0.6875rem;
  }

  /* Dropdown body */
  .dropdown-body {
    max-height: 22rem;
    overflow-y: auto;
  }

  .dropdown-message {
    padding: 1.5rem 1rem;
    text-align: center;
    font-family: var(--font-mono);
    font-size: 0.8125rem;
    color: var(--text-dim);
  }

  .browse-link {
    display: block;
    margin-top: 0.5rem;
    color: var(--color-accent);
    text-decoration: underline;
  }

  .error-msg {
    color: var(--color-error);
  }

  /* Suggestion rows */
  .suggestion-row {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    min-height: 3rem;
    padding: 0.5rem 0.875rem;
    text-decoration: none;
    color: var(--text);
    border-bottom: var(--border-width) solid var(--color-border);
    border-left: 3px solid transparent;
    background: var(--bg-surface);
    transition: background var(--motion-fast) ease, border-left-color var(--motion-fast) ease;
  }

  .suggestion-row:last-child {
    border-bottom: none;
  }

  .suggestion-row:hover,
  .suggestion-row.row-active {
    background: var(--bg-elevated);
    border-left-color: var(--color-accent);
  }

  .thumb-wrap {
    flex-shrink: 0;
  }

  .suggestion-thumb {
    width: 2rem;
    height: 2.75rem;
    object-fit: cover;
    border: var(--border-width) solid var(--color-border);
  }

  .suggestion-thumb-placeholder {
    width: 2rem;
    height: 2.75rem;
    background: var(--bg-elevated);
    border: var(--border-width) solid var(--color-border);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.875rem;
  }

  .suggestion-meta {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 0.125rem;
  }

  .suggestion-title {
    font-family: var(--font-display, serif);
    font-size: 0.9375rem;
    font-weight: 600;
    color: var(--text);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .suggestion-row:hover .suggestion-title,
  .suggestion-row.row-active .suggestion-title {
    color: var(--color-accent);
  }

  .suggestion-subtitle {
    font-family: var(--font-mono);
    font-size: 0.75rem;
    color: var(--text-dim);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .suggestion-tag {
    font-family: var(--font-mono);
    font-size: 0.6875rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-dim);
    background: var(--bg-elevated);
    border: var(--border-width) solid var(--color-border);
    padding: 0.15rem 0.4rem;
    border-radius: var(--radius-sm, 2px);
    flex-shrink: 0;
  }

  /* Dropdown footer */
  .dropdown-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.5rem 0.875rem;
    background: var(--bg-surface);
    border-top: var(--border-width) solid var(--color-border);
    font-family: var(--font-mono);
    font-size: 0.75rem;
  }

  .footer-keyboard-hint {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    color: var(--text-dim);
  }

  .kbd {
    background: var(--bg-elevated);
    border: var(--border-width) solid var(--color-border);
    padding: 0 0.25rem;
    font-family: var(--font-mono);
  }

  .view-all-link {
    color: var(--color-accent);
    text-decoration: underline;
    text-underline-offset: 2px;
    font-weight: 500;
  }

  .view-all-link:hover {
    color: var(--text);
  }
</style>
