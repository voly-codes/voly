<script>
  import { MoonIcon, SunIcon, ActivityIcon } from '../../icons.js'
  import { theme } from '../../stores/themeStore.svelte.ts'

  let { taskCount = 0, totalCost = 0 } = $props()
</script>

<header class="app-header">
  <div class="brand">
    <ActivityIcon size="16" strokeWidth="2" />
    <span class="brand-name">VOLY</span>
  </div>

  <div class="header-stats">
    <span class="stat">
      <span class="stat-value">{taskCount}</span>
      <span class="stat-label">tasks</span>
    </span>
    <span class="stat-divider"></span>
    <span class="stat">
      <span class="stat-value">${totalCost.toFixed(4)}</span>
      <span class="stat-label">total cost</span>
    </span>
  </div>

  <div class="header-actions">
    <button class="icon-btn" onclick={() => theme.toggle()} title="Toggle dark mode">
      {#if theme.dark}
        <SunIcon size="14" strokeWidth="2" />
      {:else}
        <MoonIcon size="14" strokeWidth="2" />
      {/if}
    </button>
  </div>
</header>

<style>
  .app-header {
    height: var(--header-height);
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 0 12px;
    background: var(--bg-surface);
    border-bottom: 1px solid var(--border-default);
    flex-shrink: 0;
    z-index: 10;
  }

  .brand {
    display: flex;
    align-items: center;
    gap: 6px;
    color: var(--text-primary);
    font-weight: 600;
    font-size: 13px;
    flex-shrink: 0;
  }

  .brand-name { letter-spacing: -0.01em; }

  .header-stats {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-left: 8px;
    flex: 1;
  }

  .stat {
    display: flex;
    align-items: baseline;
    gap: 4px;
  }

  .stat-value {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-primary);
    font-variant-numeric: tabular-nums;
  }

  .stat-label {
    font-size: 11px;
    color: var(--text-muted);
  }

  .stat-divider {
    width: 1px;
    height: 12px;
    background: var(--border-default);
  }

  .header-actions {
    display: flex;
    align-items: center;
    gap: 4px;
    margin-left: auto;
  }

  .icon-btn {
    width: 28px;
    height: 28px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--radius-sm);
    color: var(--text-muted);
  }

  .icon-btn:hover {
    background: var(--bg-surface-hover);
    color: var(--text-primary);
  }
</style>
