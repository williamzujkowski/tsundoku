<script lang="ts">
  interface SearchItem {
    t: string; // title
    s: string; // subtitle
    u: string; // url path (relative to base)
    y: string; // type: book | author
    c: string; // cover/photo url
  }

  let { baseUrl = '/' }: { baseUrl?: string } = $props();

  let open = $state(false);
  let query = $state('');
  let items = $state<SearchItem[]>([]);
  let loaded = $state(false);
  let loadError = $state(false);
  let inputEl: HTMLInputElement;
  let modalEl: HTMLDivElement;
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

  let results = $derived(() => {
    if (query.length < 2 || !loaded) return [];
    const q = query.toLowerCase();
    return items
      .filter(item => item.t.toLowerCase().includes(q) || item.s.toLowerCase().includes(q))
      .slice(0, 12);
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
      triggerEl = (e?.currentTarget as HTMLButtonElement) ?? document.activeElement as HTMLButtonElement | null;
      query = '';
      activeIndex = -1;
      void loadIndex();
      setTimeout(() => inputEl?.focus(), 50);
    }
  }

  function close() {
    open = false;
    query = '';
    activeIndex = -1;
    // Restore focus to whatever opened the modal so screen-reader and keyboard users land back at the trigger.
    triggerEl?.focus();
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'k' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      toggle();
    }
    if (e.key === 'Escape' && open) {
      close();
    }
    if (open) trapTab(e);
  }

  function handleResultKeydown(e: KeyboardEvent) {
    const r = results();
    if (r.length === 0) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      activeIndex = activeIndex < r.length - 1 ? activeIndex + 1 : 0;
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      activeIndex = activeIndex > 0 ? activeIndex - 1 : r.length - 1;
    } else if (e.key === 'Enter' && activeIndex >= 0) {
      e.preventDefault();
      window.location.href = `${baseUrl}${r[activeIndex].u}`;
    }
  }
</script>

<svelte:window onkeydown={handleKeydown} />

<button
  onclick={toggle}
  class="search-toggle"
  aria-label="Search (⌘K)"
  title="Search (⌘K)"
>
  <svg class="search-toggle-icon" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" aria-hidden="true">
    <path stroke-linecap="round" stroke-linejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
  </svg>
</button>

{#if open}
  <div
    class="overlay"
    onclick={close}
    onkeydown={(e) => e.key === 'Escape' && close()}
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
        <svg class="modal-search-icon" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
        </svg>
        <input
          bind:this={inputEl}
          bind:value={query}
          type="search"
          placeholder="Search books and authors..."
          class="modal-search-input"
          aria-label="Search query"
          aria-controls="search-results"
          aria-activedescendant={activeIndex >= 0 ? `search-result-${activeIndex}` : undefined}
          onkeydown={handleResultKeydown}
        />
        <kbd class="kbd-hint">ESC</kbd>
      </div>

      <div id="search-results" class="results-list" role="listbox">
        {#if loadError}
          <div class="results-message results-error">Failed to load search index. Try refreshing the page.</div>
        {:else if !loaded}
          <div class="results-message">Loading search index...</div>
        {:else if query.length < 2}
          <div class="results-message">Type at least 2 characters...</div>
        {:else if results().length === 0}
          <div class="results-message results-empty">No results for "{query}"</div>
        {:else}
          {#each results() as item, i}
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
              <span class="result-type">{item.y}</span>
            </a>
          {/each}
        {/if}
      </div>

      <div class="modal-footer">
        <div class="keyboard-hints">
          <span><kbd class="kbd">↑↓</kbd> navigate</span>
          <span><kbd class="kbd">↵</kbd> select</span>
          <span><kbd class="kbd">esc</kbd> close</span>
        </div>
        {#if loaded && query.length >= 2}
          <span class="results-count" aria-live="polite">{results().length} {results().length === 1 ? 'result' : 'results'}</span>
        {/if}
      </div>
    </div>
  </div>
{/if}

<style>
  .search-toggle {
    padding: 0.5rem;
    color: var(--text-muted);
    background: none;
    border: none;
    cursor: pointer;
  }

  .search-toggle:hover {
    color: var(--text);
  }

  .search-toggle-icon {
    width: 1.25rem;
    height: 1.25rem;
  }

  /* --- Overlay --- */
  .overlay {
    position: fixed;
    inset: 0;
    z-index: 60;
    background: rgba(0, 0, 0, 0.6);
    backdrop-filter: blur(4px);
  }

  /* --- Modal --- */
  .modal {
    max-width: 32rem;
    margin: 15vh auto 0;
    background: var(--bg-surface);
    border: var(--border-width) solid var(--border);
    box-shadow: 8px 8px 0 var(--shadow-color);
    overflow: hidden;
  }

  /* --- Search bar inside modal --- */
  .modal-search-bar {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0 1rem;
    border-bottom: var(--border-width) solid var(--border);
  }

  .modal-search-icon {
    width: 1.25rem;
    height: 1.25rem;
    color: var(--text-dim);
    flex-shrink: 0;
  }

  .modal-search-input {
    width: 100%;
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
  }

  .kbd-hint {
    display: none;
    font-size: 0.625rem;
    color: var(--text-dim);
    background: var(--bg-elevated);
    padding: 0.125rem 0.375rem;
    border: var(--border-width) solid var(--border);
    font-family: var(--font-mono);
  }

  @media (min-width: 640px) {
    .kbd-hint {
      display: inline;
    }
  }

  /* --- Results list --- */
  .results-list {
    max-height: 50vh;
    overflow-y: auto;
  }

  .results-message {
    padding: 2rem 1rem;
    text-align: center;
    font-size: 0.875rem;
    color: var(--text-dim);
  }

  .results-error {
    color: var(--pop-red);
  }

  .results-empty {
    color: var(--text-dim);
  }

  /* --- Individual result --- */
  .result-item {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.625rem 1rem;
    text-decoration: none;
    color: var(--text);
    border-left: 3px solid transparent;
    transition: border-color 80ms ease, background 80ms ease;
  }

  .result-item:hover,
  .result-item.result-active {
    background: var(--bg-elevated);
    border-left-color: var(--pop-pink);
    color: var(--text);
  }

  .result-thumb {
    width: 2rem;
    height: 2.75rem;
    object-fit: cover;
    flex-shrink: 0;
    border: 1px solid var(--border);
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
    font-size: 0.75rem;
    border: 1px solid var(--border);
  }

  .result-text {
    min-width: 0;
    flex: 1;
  }

  .result-title {
    font-size: 0.875rem;
    color: var(--text);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .result-subtitle {
    font-size: 0.75rem;
    color: var(--text-dim);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .result-type {
    font-size: 0.625rem;
    color: var(--text-dim);
    text-transform: uppercase;
    flex-shrink: 0;
  }

  /* --- Modal footer --- */
  .modal-footer {
    padding: 0.5rem 1rem;
    border-top: var(--border-width) solid var(--border);
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .keyboard-hints {
    font-size: 0.625rem;
    color: var(--text-dim);
    display: flex;
    gap: 1rem;
  }

  .kbd {
    background: var(--bg-elevated);
    padding: 0 0.25rem;
    border: 1px solid var(--border);
    font-family: var(--font-mono);
  }

  .results-count {
    font-size: 0.625rem;
    color: var(--text-dim);
  }
</style>
