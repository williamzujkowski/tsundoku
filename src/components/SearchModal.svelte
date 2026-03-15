<script lang="ts">
  interface SearchItem {
    title: string;
    subtitle: string;
    url: string;
    type: 'book' | 'author';
    cover_url?: string;
  }

  let { items = [], baseUrl = '/' }: { items: SearchItem[]; baseUrl?: string } = $props();

  let open = $state(false);
  let query = $state('');
  let inputEl: HTMLInputElement;

  let results = $derived(() => {
    if (query.length < 2) return [];
    const q = query.toLowerCase();
    return items
      .filter(item => item.title.toLowerCase().includes(q) || item.subtitle.toLowerCase().includes(q))
      .slice(0, 12);
  });

  function toggle() {
    open = !open;
    if (open) {
      query = '';
      setTimeout(() => inputEl?.focus(), 50);
    }
  }

  function close() {
    open = false;
    query = '';
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
</script>

<svelte:window onkeydown={handleKeydown} />

<!-- Search trigger button -->
<button
  onclick={toggle}
  class="p-2 text-gray-400 hover:text-white transition-colors"
  aria-label="Search (⌘K)"
  title="Search (⌘K)"
>
  <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
    <path stroke-linecap="round" stroke-linejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
  </svg>
</button>

<!-- Modal overlay -->
{#if open}
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="fixed inset-0 z-[60] bg-black/60 backdrop-blur-sm"
    onclick={close}
    onkeydown={(e) => e.key === 'Escape' && close()}
  >
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div
      class="max-w-lg mx-auto mt-[15vh] bg-gray-900 border border-gray-700 rounded-xl shadow-2xl overflow-hidden"
      onclick={(e) => e.stopPropagation()}
      onkeydown={() => {}}
    >
      <!-- Search input -->
      <div class="flex items-center gap-3 px-4 border-b border-gray-800">
        <svg class="w-5 h-5 text-gray-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
        </svg>
        <input
          bind:this={inputEl}
          bind:value={query}
          type="search"
          placeholder="Search books and authors..."
          class="w-full bg-transparent text-white py-3 text-base outline-none placeholder:text-gray-600"
        />
        <kbd class="hidden sm:inline text-[10px] text-gray-600 bg-gray-800 px-1.5 py-0.5 rounded border border-gray-700">ESC</kbd>
      </div>

      <!-- Results -->
      <div class="max-h-[50vh] overflow-y-auto">
        {#if query.length < 2}
          <div class="px-4 py-8 text-center text-sm text-gray-600">
            Type at least 2 characters to search...
          </div>
        {:else if results().length === 0}
          <div class="px-4 py-8 text-center text-sm text-gray-500">
            No results for "{query}"
          </div>
        {:else}
          {#each results() as item}
            <a
              href={item.url}
              class="flex items-center gap-3 px-4 py-2.5 hover:bg-gray-800/60 transition-colors"
              onclick={close}
            >
              {#if item.cover_url}
                <img src={item.cover_url} alt="" class="w-8 h-11 rounded object-cover shrink-0" />
              {:else}
                <div class="w-8 h-11 rounded bg-gray-800 shrink-0 flex items-center justify-center text-gray-700 text-xs">
                  {item.type === 'book' ? '📖' : '👤'}
                </div>
              {/if}
              <div class="min-w-0 flex-1">
                <p class="text-sm text-white truncate">{item.title}</p>
                <p class="text-xs text-gray-500 truncate">{item.subtitle}</p>
              </div>
              <span class="text-[10px] text-gray-600 uppercase shrink-0">{item.type}</span>
            </a>
          {/each}
        {/if}
      </div>

      <!-- Footer -->
      <div class="px-4 py-2 border-t border-gray-800 text-[10px] text-gray-600 flex gap-4">
        <span><kbd class="bg-gray-800 px-1 rounded">↵</kbd> to select</span>
        <span><kbd class="bg-gray-800 px-1 rounded">esc</kbd> to close</span>
        <span><kbd class="bg-gray-800 px-1 rounded">⌘K</kbd> to search</span>
      </div>
    </div>
  </div>
{/if}
