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

  let filtered = $derived(
    books.filter(b => {
      const matchesSearch = search === '' ||
        b.title.toLowerCase().includes(search.toLowerCase()) ||
        b.author.toLowerCase().includes(search.toLowerCase());
      const matchesCategory = selectedCategory === '' || b.category === selectedCategory;
      const matchesPriority = selectedPriority === 0 || b.priority === selectedPriority;
      return matchesSearch && matchesCategory && matchesPriority;
    })
  );

  let sortedBooks = $derived([...filtered].sort((a, b) => a.title.localeCompare(b.title)));

  function priorityClass(p: number): string {
    if (p === 1) return 'bg-purple-900 text-purple-300';
    if (p === 2) return 'bg-gray-800 text-gray-400';
    return 'bg-gray-800 text-gray-500';
  }
</script>

<div class="space-y-6">
  <!-- Search and filters -->
  <div class="flex flex-col sm:flex-row gap-3">
    <input
      type="text"
      placeholder="Search books or authors..."
      bind:value={search}
      class="flex-1 rounded-lg bg-gray-800 border border-gray-700 text-white px-4 py-2 text-sm focus:outline-none focus:border-purple-500"
    />
    <select bind:value={selectedCategory}
      class="rounded-lg bg-gray-800 border border-gray-700 text-white px-4 py-2 text-sm">
      <option value="">All Categories</option>
      {#each categories as cat}
        <option value={cat}>{cat}</option>
      {/each}
    </select>
    <select bind:value={selectedPriority}
      class="rounded-lg bg-gray-800 border border-gray-700 text-white px-4 py-2 text-sm">
      <option value={0}>All Priorities</option>
      <option value={1}>Must-Read (P1)</option>
      <option value={2}>Recommended (P2)</option>
      <option value={3}>Supplementary (P3)</option>
    </select>
  </div>

  <!-- Results count -->
  <p class="text-sm text-gray-500">
    Showing {Math.min(sortedBooks.length, 100)} of {books.length} books
    {#if sortedBooks.length !== books.length}
      ({sortedBooks.length} matched)
    {/if}
  </p>

  <!-- Book grid -->
  <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
    {#each sortedBooks.slice(0, 100) as book (book.slug)}
      <div class="rounded-xl border border-gray-800 bg-gray-900 p-4 hover:border-purple-800 transition-colors">
        <div class="flex items-start justify-between mb-2">
          <span class="text-xs px-2 py-0.5 rounded-full {priorityClass(book.priority)}">
            P{book.priority}
          </span>
          <span class="text-xs text-gray-600">{book.category}</span>
        </div>
        <h3 class="text-white font-medium text-sm mb-1 line-clamp-2">{book.title}</h3>
        <p class="text-gray-500 text-xs">{book.author}</p>
      </div>
    {/each}
  </div>

  {#if sortedBooks.length > 100}
    <p class="text-center text-sm text-gray-500">
      Showing first 100 results. Use search or filters to narrow down.
    </p>
  {/if}
</div>
