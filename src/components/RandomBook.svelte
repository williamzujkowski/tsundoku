<script lang="ts">
  let { baseUrl = '/' }: { baseUrl?: string } = $props();

  async function goToRandom() {
    try {
      // Tiny dedicated index (KB, not the ~1MB search index) of book URL paths.
      const res = await fetch(`${baseUrl}random-slugs.json`);
      if (!res.ok) return;
      const slugs: string[] = await res.json();
      if (slugs.length === 0) return;
      const idx = Math.floor(Math.random() * slugs.length);
      window.location.href = `${baseUrl}${slugs[idx]}`;
    } catch {
      // Silently fail — button just doesn't navigate
    }
  }
</script>

<button
  onclick={goToRandom}
  class="random-btn"
  aria-label="Discover a random book"
  title="Random book"
>
  <svg class="random-icon" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" aria-hidden="true">
    <path stroke-linecap="round" stroke-linejoin="round" d="M19.5 12c0-1.232-.046-2.453-.138-3.662a4.006 4.006 0 0 0-3.7-3.7 48.678 48.678 0 0 0-7.324 0 4.006 4.006 0 0 0-3.7 3.7c-.017.22-.032.441-.046.662M19.5 12l3-3m-3 3-3-3m-12 3c0 1.232.046 2.453.138 3.662a4.006 4.006 0 0 0 3.7 3.7 48.656 48.656 0 0 0 7.324 0 4.006 4.006 0 0 0 3.7-3.7c.017-.22.032-.441.046-.662M4.5 12l3 3m-3-3-3 3" />
  </svg>
</button>

<style>
  .random-btn {
    min-width: 2.75rem;
    min-height: 2.75rem;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    color: var(--text-muted);
    background: none;
    border: none;
    cursor: pointer;
    transition: color 120ms ease;
  }

  .random-btn:hover {
    color: var(--text);
  }

  .random-icon {
    width: 1.25rem;
    height: 1.25rem;
  }
</style>
