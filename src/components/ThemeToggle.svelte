<script lang="ts">
  import { onMount } from 'svelte';

  type Theme = 'light' | 'dark';

  let theme = $state<Theme>('dark');

  function readCurrentTheme(): Theme {
    if (typeof document === 'undefined') return 'dark';
    const attr = document.documentElement.getAttribute('data-theme');
    if (attr === 'light' || attr === 'dark') return attr;
    return window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
  }

  function applyTheme(next: Theme) {
    document.documentElement.setAttribute('data-theme', next);
    try {
      localStorage.setItem('theme', next);
    } catch {
      // localStorage may be unavailable (private mode); fall through
    }
    theme = next;
  }

  function toggle() {
    applyTheme(theme === 'dark' ? 'light' : 'dark');
  }

  onMount(() => {
    theme = readCurrentTheme();
    // Sync across page transitions in case the inline pre-paint script ran with a different value
    const handler = () => { theme = readCurrentTheme(); };
    document.addEventListener('astro:after-swap', handler);
    return () => document.removeEventListener('astro:after-swap', handler);
  });
</script>

<button
  type="button"
  class="theme-toggle"
  onclick={toggle}
  aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
  title={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
>
  {#if theme === 'dark'}
    <svg class="theme-icon" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" aria-hidden="true">
      <path stroke-linecap="round" stroke-linejoin="round" d="M12 3v2.25m6.364.386-1.591 1.591M21 12h-2.25m-.386 6.364-1.591-1.591M12 18.75V21m-4.773-4.227-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0Z" />
    </svg>
  {:else}
    <svg class="theme-icon" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" aria-hidden="true">
      <path stroke-linecap="round" stroke-linejoin="round" d="M21.752 15.002A9.72 9.72 0 0 1 18 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 0 0 3 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 0 0 9.002-5.998Z" />
    </svg>
  {/if}
</button>

<style>
  .theme-toggle {
    padding: 0.5rem;
    color: var(--text-muted);
    background: none;
    border: none;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }

  .theme-toggle:hover {
    color: var(--text);
  }

  .theme-icon {
    width: 1.25rem;
    height: 1.25rem;
    animation: theme-pop 220ms cubic-bezier(0.2, 0.85, 0.3, 1.05);
  }

  @keyframes theme-pop {
    0%   { opacity: 0; transform: rotate(-45deg) scale(0.6); }
    60%  { opacity: 1; transform: rotate(8deg) scale(1.08); }
    100% { transform: rotate(0) scale(1); }
  }

  @media (prefers-reduced-motion: reduce) {
    .theme-icon { animation: none; }
  }
</style>
