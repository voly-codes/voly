<script>
  let { title = '', collapsible = false, expanded = $bindable(true), chip = '', children } = $props()
</script>

<div class="extras-section">
  {#if collapsible}
    <button class="section-toggle" onclick={() => expanded = !expanded}>
      <span class="section-title">{title}</span>
      {#if chip}
        <span class="toggle-chip">{chip}</span>
      {/if}
      <span class="toggle-arrow" class:rotated={!expanded}>›</span>
    </button>
    {#if expanded}
      {@render children()}
    {/if}
  {:else}
    <div class="section-title">{title}</div>
    {@render children()}
  {/if}
</div>

<style>
  .extras-section {
    margin-top: 16px;
    padding-top: 12px;
    border-top: 1px solid var(--border-muted);
  }

  .section-title {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-muted);
    margin-bottom: 7px;
  }

  .section-toggle {
    display: flex;
    align-items: center;
    gap: 6px;
    width: 100%;
    text-align: left;
    background: transparent;
    padding: 0;
    margin-bottom: 0;
    cursor: pointer;
  }

  .section-toggle:hover .section-title { color: var(--text-primary); }

  .toggle-arrow {
    font-size: 14px;
    color: var(--text-muted);
    margin-left: auto;
    transition: transform 0.15s;
    line-height: 1;
  }
  .toggle-arrow.rotated { transform: rotate(90deg); }

  .toggle-chip {
    font-size: 10px;
    color: var(--text-muted);
    background: var(--bg-inset);
    border-radius: 3px;
    padding: 1px 5px;
    font-variant-numeric: tabular-nums;
  }
</style>
