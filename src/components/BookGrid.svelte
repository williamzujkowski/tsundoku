<script lang="ts">
  interface Book {
    title: string;
    author: string;
    category: string;
    priority: number;
    slug: string;
  }

  let { books = [], categories = [] }: { books: Book[]; categories: string[] } = $props();

  let search = $state('');
  let selectedCategory = $state('');
  let selectedPriority = $state(0);
  let showCount = $state(100);

  let filtered = $derived(
    books.filter(b => {
      const q = search.toLowerCase();
      const matchesSearch = q === '' ||
        b.title.toLowerCase().includes(q) ||
        b.author.toLowerCase().includes(q);
      const matchesCategory = selectedCategory === '' || b.category === selectedCategory;
      const matchesPriority = selectedPriority === 0 || b.priority === selectedPriority;
      return matchesSearch && matchesCategory && matchesPriority;
    })
  );

  let sortedBooks = $derived([...filtered].sort((a, b) => a.title.localeCompare(b.title)));

  function priorityLabel(p: number): string {
    if (p === 1) return 'Must-Read';
    if (p === 2) return 'Recommended';
    return 'Supplementary';
  }

  function priorityClass(p: number): string {
    if (p === 1) return 'bg-purple-900/60 text-purple-300 border border-purple-700/30';
    if (p === 2) return 'bg-gray-800 text-gray-400';
    return 'bg-gray-800/50 text-gray-500';
  }

  function clearFilters() {
    search = '';
    selectedCategory = '';
    selectedPriority = 0;
  }

  function loadMore() {
    showCount += 100;
  }
</script>

<div class="space-y-4 sm:space-y-6">
  <!-- Search and filters -->
  <div class="space-y-2 sm:space-y-0 sm:flex sm:flex-row sm:gap-3">
    <div class="relative flex-1">
      <input
        type="search"
        placeholder="Search books or authors..."
        bind:value={search}
        aria-label="Search books by title or author"
        class="w-full rounded-lg bg-gray-800 border border-gray-700 text-white pl-10 pr-4 py-2.5 text-base sm:text-sm focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500 transition-colors"
      />
      <svg class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
      </svg>
    </div>
    <div class="flex gap-2">
      <select bind:value={selectedCategory}
        aria-label="Filter by category"
        class="flex-1 sm:flex-none rounded-lg bg-gray-800 border border-gray-700 text-white px-3 py-2.5 text-sm focus:outline-none focus:border-purple-500 truncate">
        <option value="">All Categories</option>
        {#each categories as cat}
          <option value={cat}>{cat}</option>
        {/each}
      </select>
      <select bind:value={selectedPriority}
        aria-label="Filter by priority"
        class="flex-1 sm:flex-none rounded-lg bg-gray-800 border border-gray-700 text-white px-3 py-2.5 text-sm focus:outline-none focus:border-purple-500">
        <option value={0}>All Priorities</option>
        <option value={1}>Must-Read</option>
        <option value={2}>Recommended</option>
        <option value={3}>Supplementary</option>
      </select>
    </div>
  </div>

  <!-- Results bar -->
  <div class="flex items-center justify-between">
    <p class="text-sm text-gray-500">
      {#if sortedBooks.length === books.length}
        {books.length.toLocaleString()} books
      {:else}
        {sortedBooks.length.toLocaleString()} of {books.length.toLocaleString()} books
      {/if}
    </p>
    {#if search !== '' || selectedCategory !== '' || selectedPriority !== 0}
      <button onclick={clearFilters}
        class="text-sm text-purple-400 hover:text-purple-300 transition-colors">
        Clear filters
      </button>
    {/if}
  </div>

  <!-- Empty state -->
  {#if sortedBooks.length === 0}
    <div class="rounded-xl border border-gray-800 bg-gray-900 p-8 sm:p-12 text-center">
      <p class="text-gray-400 text-lg mb-2">No books found</p>
      <p class="text-gray-500 text-sm mb-4">Try adjusting your search or filters.</p>
      <button onclick={clearFilters}
        class="inline-flex items-center justify-center rounded-lg bg-purple-600 hover:bg-purple-500 text-white font-semibold px-6 py-2.5 text-sm transition-colors">
        Clear all filters
      </button>
    </div>
  {:else}
    <!-- Book grid -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
      {#each sortedBooks.slice(0, showCount) as book (book.slug)}
        <article class="rounded-xl border border-gray-800 bg-gray-900 p-4 hover:border-purple-800/60 transition-colors group">
          <div class="flex items-start justify-between mb-2 gap-2">
            <span class="text-[11px] px-2 py-0.5 rounded-full whitespace-nowrap {priorityClass(book.priority)}">
              {priorityLabel(book.priority)}
            </span>
            <span class="text-[11px] text-gray-600 truncate">{book.category}</span>
          </div>
          <h3 class="text-white font-medium text-sm mb-1 line-clamp-2 group-hover:text-purple-200 transition-colors">{book.title}</h3>
          <p class="text-gray-500 text-xs">{book.author}</p>
        </article>
      {/each}
    </div>

    <!-- Load more -->
    {#if sortedBooks.length > showCount}
      <div class="text-center pt-4">
        <button onclick={loadMore}
          class="inline-flex items-center justify-center rounded-lg border border-gray-700 hover:border-purple-700 text-gray-300 hover:text-white font-semibold px-6 py-2.5 text-sm transition-colors">
          Show more ({Math.min(100, sortedBooks.length - showCount)} remaining)
        </button>
      </div>
    {/if}
  {/if}
</div>
