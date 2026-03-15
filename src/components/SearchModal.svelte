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
  let activeIndex = $state(-1);

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

  function toggle() {
    open = !open;
    if (open) {
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
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'k' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      toggle();
    }
    if (e.key === 'Escape' && open) {
      close();
    }
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
  class="p-2 text-gray-400 hover:text-white transition-colors"
  aria-label="Search (⌘K)"
  title="Search (⌘K)"
>
  <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" aria-hidden="true">
    <path stroke-linecap="round" stroke-linejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
  </svg>
</button>

{#if open}
  <div
    class="fixed inset-0 z-[60] bg-black/60 backdrop-blur-sm"
    onclick={close}
    onkeydown={(e) => e.key === 'Escape' && close()}
    role="presentation"
  >
    <div
      class="max-w-lg mx-auto mt-[15vh] bg-gray-900 border border-gray-700 rounded-xl shadow-2xl overflow-hidden"
      onclick={(e) => e.stopPropagation()}
      role="dialog"
      aria-modal="true"
      aria-label="Search books and authors"
    >
      <div class="flex items-center gap-3 px-4 border-b border-gray-800">
        <svg class="w-5 h-5 text-gray-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
        </svg>
        <input
          bind:this={inputEl}
          bind:value={query}
          type="search"
          placeholder="Search books and authors..."
          class="w-full bg-transparent text-white py-3 text-base outline-none placeholder:text-gray-600"
          aria-label="Search query"
          aria-controls="search-results"
          aria-activedescendant={activeIndex >= 0 ? `search-result-${activeIndex}` : undefined}
          onkeydown={handleResultKeydown}
        />
        <kbd class="hidden sm:inline text-[10px] text-gray-600 bg-gray-800 px-1.5 py-0.5 rounded border border-gray-700">ESC</kbd>
      </div>

      <div id="search-results" class="max-h-[50vh] overflow-y-auto" role="listbox">
        {#if loadError}
          <div class="px-4 py-8 text-center text-sm text-red-400">Failed to load search index. Try refreshing the page.</div>
        {:else if !loaded}
          <div class="px-4 py-8 text-center text-sm text-gray-600">Loading search index...</div>
        {:else if query.length < 2}
          <div class="px-4 py-8 text-center text-sm text-gray-600">Type at least 2 characters...</div>
        {:else if results().length === 0}
          <div class="px-4 py-8 text-center text-sm text-gray-500">No results for "{query}"</div>
        {:else}
          {#each results() as item, i}
            <a
              id="search-result-{i}"
              href="{baseUrl}{item.u}"
              class="flex items-center gap-3 px-4 py-2.5 transition-colors {i === activeIndex ? 'bg-purple-900/40 border-l-2 border-purple-500' : 'hover:bg-gray-800/60 border-l-2 border-transparent'}"
              role="option"
              aria-selected={i === activeIndex}
              onclick={close}
              onmouseenter={() => activeIndex = i}
            >
              {#if item.c}
                <img src={item.c} alt="" class="w-8 h-11 rounded object-cover shrink-0" loading="lazy" />
              {:else}
                <div class="w-8 h-11 rounded bg-gray-800 shrink-0 flex items-center justify-center text-gray-700 text-xs" aria-hidden="true">
                  {item.y === 'book' ? '📖' : '👤'}
                </div>
              {/if}
              <div class="min-w-0 flex-1">
                <p class="text-sm text-white truncate">{item.t}</p>
                <p class="text-xs text-gray-500 truncate">{item.s}</p>
              </div>
              <span class="text-[10px] text-gray-600 uppercase shrink-0">{item.y}</span>
            </a>
          {/each}
        {/if}
      </div>

      <div class="px-4 py-2 border-t border-gray-800 flex items-center justify-between">
        <div class="text-[10px] text-gray-600 flex gap-4">
          <span><kbd class="bg-gray-800 px-1 rounded">↑↓</kbd> navigate</span>
          <span><kbd class="bg-gray-800 px-1 rounded">↵</kbd> select</span>
          <span><kbd class="bg-gray-800 px-1 rounded">esc</kbd> close</span>
        </div>
        {#if loaded && query.length >= 2}
          <span class="text-[10px] text-gray-600" aria-live="polite">{results().length} {results().length === 1 ? 'result' : 'results'}</span>
        {/if}
      </div>
    </div>
  </div>
{/if}
