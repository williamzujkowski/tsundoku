<script lang="ts">
  interface Book {
    title: string;
    author: string;
    category: string;
    priority: number;
    slug: string;
    cover_url?: string;
    first_published?: number;
    reading_status?: 'want' | 'reading' | 'read';
  }

  let { books = [], categories = [], baseUrl = '/' }: { books: Book[]; categories: string[]; baseUrl?: string } = $props();

  let search = $state('');
  let selectedCategory = $state('');
  let selectedPriority = $state(0);
  let selectedStatus = $state('');
  let showCount = $state(100);

  let filtered = $derived(
    books.filter(b => {
      const q = search.toLowerCase();
      const matchesSearch = q === '' ||
        b.title.toLowerCase().includes(q) ||
        b.author.toLowerCase().includes(q);
      const matchesCategory = selectedCategory === '' || b.category === selectedCategory;
      const matchesPriority = selectedPriority === 0 || b.priority === selectedPriority;
      const matchesStatus = selectedStatus === '' || b.reading_status === selectedStatus;
      return matchesSearch && matchesCategory && matchesPriority && matchesStatus;
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
    selectedStatus = '';
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
      <select bind:value={selectedStatus}
        aria-label="Filter by reading status"
        class="flex-1 sm:flex-none rounded-lg bg-gray-800 border border-gray-700 text-white px-3 py-2.5 text-sm focus:outline-none focus:border-purple-500">
        <option value="">All Status</option>
        <option value="read">✓ Read</option>
        <option value="reading">📖 Reading</option>
        <option value="want">📋 Want to Read</option>
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
    {#if search !== '' || selectedCategory !== '' || selectedPriority !== 0 || selectedStatus !== ''}
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
        <a href="{baseUrl}books/{book.slug}/"
           class="rounded-xl border border-gray-800 bg-gray-900 p-3 hover:border-purple-800/60 hover:shadow-lg hover:shadow-purple-900/20 transition-all duration-200 group block">
          <div class="flex gap-3">
            {#if book.cover_url}
              <img src={book.cover_url} alt="" class="w-12 h-[4.5rem] rounded object-cover shrink-0 group-hover:scale-105 transition-transform duration-200" loading="lazy" />
            {:else}
              <div class="w-12 h-[4.5rem] rounded bg-gradient-to-br from-purple-900/30 to-gray-800 shrink-0 flex items-center justify-center text-gray-700 text-lg">📖</div>
            {/if}
            <div class="min-w-0 flex-1">
              <div class="flex items-start justify-between gap-1 mb-1">
                <span class="text-[10px] px-1.5 py-0.5 rounded-full whitespace-nowrap {priorityClass(book.priority)}">
                  {priorityLabel(book.priority)}
                </span>
                {#if book.first_published}
                  <span class="text-[10px] text-gray-600">{book.first_published}</span>
                {/if}
              </div>
              <h3 class="text-white font-medium text-sm mb-0.5 line-clamp-2 group-hover:text-purple-200 transition-colors">{book.title}</h3>
              <p class="text-gray-500 text-xs truncate">{book.author}</p>
              <div class="flex items-center gap-1 mt-0.5">
                <p class="text-[10px] text-gray-600 truncate">{book.category}</p>
                {#if book.reading_status}
                  <span class="text-[10px] shrink-0 {book.reading_status === 'read' ? 'text-green-500' : book.reading_status === 'reading' ? 'text-amber-500' : 'text-blue-500'}">
                    {book.reading_status === 'read' ? '✓' : book.reading_status === 'reading' ? '📖' : '📋'}
                  </span>
                {/if}
              </div>
            </div>
          </div>
        </a>
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
