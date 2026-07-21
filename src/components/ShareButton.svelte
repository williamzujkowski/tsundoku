<script lang="ts">
  let { title = '', url = '' }: { title?: string; url?: string } = $props();
  let copied = $state(false);

  async function share() {
    const shareData = { title, url };

    if (typeof navigator !== 'undefined' && navigator.share) {
      try {
        await navigator.share(shareData);
        return;
      } catch {
        // User cancelled or API unavailable — fall through to clipboard
      }
    }

    // Clipboard fallback
    try {
      await navigator.clipboard.writeText(url);
      copied = true;
      setTimeout(() => copied = false, 2000);
    } catch {
      // Clipboard API unavailable
    }
  }
</script>

<button
  onclick={share}
  class="share-btn"
  aria-label="Share this book"
>
  {#if copied}
    <svg class="share-icon share-icon-copied" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" aria-hidden="true">
      <path stroke-linecap="round" stroke-linejoin="round" d="m4.5 12.75 6 6 9-13.5" />
    </svg>
    Copied!
  {:else}
    <svg class="share-icon" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" aria-hidden="true">
      <path stroke-linecap="round" stroke-linejoin="round" d="M7.217 10.907a2.25 2.25 0 1 0 0 2.186m0-2.186c.18.324.283.696.283 1.093s-.103.77-.283 1.093m0-2.186 9.566-5.314m-9.566 7.5 9.566 5.314m0 0a2.25 2.25 0 1 0 3.935 2.186 2.25 2.25 0 0 0-3.935-2.186Zm0-12.814a2.25 2.25 0 1 0 3.935-2.186 2.25 2.25 0 0 0-3.935 2.186Z" />
    </svg>
    Share
  {/if}
</button>

<style>
  .share-btn {
    display: inline-flex;
    align-items: center;
    gap: 0.375rem;
    min-height: 2.75rem;
    font-size: 0.875rem;
    padding: 0.375rem 0.875rem;
    background: transparent;
    color: var(--text-muted);
    border: var(--border-width) solid var(--border-strong);
    border-radius: var(--radius-sm);
    cursor: pointer;
    font-family: var(--font-body);
    transition: border-color 120ms ease, color 120ms ease;
  }

  .share-btn:hover {
    border-color: var(--pop-pink);
    color: var(--pop-pink);
  }

  .share-icon {
    width: 0.875rem;
    height: 0.875rem;
  }

  .share-icon-copied {
    color: var(--pop-green);
  }
</style>
