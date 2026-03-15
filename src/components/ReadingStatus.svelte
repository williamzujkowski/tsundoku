<script lang="ts">
  let { slug = '' }: { slug: string } = $props();

  type Status = 'none' | 'want' | 'reading' | 'read';

  const STORAGE_KEY = 'tsundoku-reading-status';

  function getStatuses(): Record<string, Status> {
    if (typeof window === 'undefined') return {};
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch {
      return {};
    }
  }

  function saveStatus(bookSlug: string, status: Status) {
    const statuses = getStatuses();
    if (status === 'none') {
      delete statuses[bookSlug];
    } else {
      statuses[bookSlug] = status;
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(statuses));
  }

  let currentStatus = $state<Status>('none');

  // Load on mount
  $effect(() => {
    const statuses = getStatuses();
    currentStatus = statuses[slug] || 'none';
  });

  function setStatus(status: Status) {
    currentStatus = status === currentStatus ? 'none' : status;
    saveStatus(slug, currentStatus);
  }

  const buttons: { status: Status; label: string; icon: string; activeClass: string }[] = [
    { status: 'want', label: 'Want to Read', icon: '📋', activeClass: 'bg-blue-900/40 border-blue-700/50 text-blue-300' },
    { status: 'reading', label: 'Reading', icon: '📖', activeClass: 'bg-amber-900/40 border-amber-700/50 text-amber-300' },
    { status: 'read', label: 'Read', icon: '✓', activeClass: 'bg-green-900/40 border-green-700/50 text-green-300' },
  ];
</script>

<div class="flex gap-2">
  {#each buttons as btn}
    <button
      onclick={() => setStatus(btn.status)}
      class="text-xs px-2.5 py-1.5 rounded-lg border transition-all duration-200 {currentStatus === btn.status
        ? btn.activeClass
        : 'border-gray-700 text-gray-500 hover:border-gray-600 hover:text-gray-400'}"
      aria-pressed={currentStatus === btn.status}
      aria-label={btn.label}
    >
      <span class="mr-1">{btn.icon}</span>{btn.label}
    </button>
  {/each}
</div>
