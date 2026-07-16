<script>
  /**
   * Light readiness banner — providers, CLIs, cwd, optional cloud link.
   * Does not block the UI; shows how to fix warn/error checks.
   */
  let {
    report = null,
    loading = false,
    onRefresh = undefined,
  } = $props()

  let dismissed = $state(false)
  let expanded = $state(false)

  let issues = $derived(
    (report?.checks ?? []).filter((c) => c.status === 'error' || c.status === 'warn')
  )
  let tone = $derived(
    !report ? 'muted'
      : report.ready && issues.length === 0 ? 'ok'
      : report.ready ? 'warn'
      : 'error'
  )

  function refresh() {
    dismissed = false
    onRefresh?.()
  }
</script>

{#if !dismissed}
  <div class="env-banner" class:tone-ok={tone === 'ok'} class:tone-warn={tone === 'warn'} class:tone-error={tone === 'error'}>
    <div class="env-row">
      <div class="env-main">
        <span class="env-label">Environment</span>
        {#if loading && !report}
          <span class="env-summary">Checking…</span>
        {:else if report}
          <span class="env-summary">{report.summary}</span>
        {:else}
          <span class="env-summary">Could not load readiness checks</span>
        {/if}
      </div>
      <div class="env-actions">
        {#if report && issues.length > 0}
          <button type="button" class="env-link" onclick={() => (expanded = !expanded)}>
            {expanded ? 'Hide details' : `${issues.length} tip${issues.length === 1 ? '' : 's'}`}
          </button>
        {/if}
        <button type="button" class="env-link" onclick={refresh} disabled={loading}>
          {loading ? '…' : 'Recheck'}
        </button>
        {#if report?.ready}
          <button type="button" class="env-link" onclick={() => (dismissed = true)} title="Dismiss for this session">
            Dismiss
          </button>
        {/if}
      </div>
    </div>

    {#if expanded && issues.length > 0}
      <ul class="env-list">
        {#each issues as c}
          <li class="env-item status-{c.status}">
            <strong>{c.label}</strong>
            <span>{c.detail}</span>
            {#if c.hint}
              <span class="env-hint">{c.hint}</span>
            {/if}
          </li>
        {/each}
      </ul>
    {/if}
  </div>
{/if}

<style>
  .env-banner {
    border-bottom: 1px solid var(--border-default);
    padding: 8px 14px;
    font-size: 12px;
    background: var(--bg-elevated, var(--bg-surface));
  }
  .tone-ok { border-left: 3px solid var(--accent-green, #3d9a6a); }
  .tone-warn { border-left: 3px solid var(--accent-amber, #c4922a); }
  .tone-error { border-left: 3px solid var(--accent-red, #c44); background: color-mix(in srgb, var(--accent-red, #c44) 6%, var(--bg-surface)); }

  .env-row {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
  }
  .env-main {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }
  .env-label {
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    font-size: 10px;
  }
  .env-summary {
    color: var(--text-primary);
    line-height: 1.35;
  }
  .env-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    flex-shrink: 0;
  }
  .env-link {
    background: none;
    border: none;
    padding: 0;
    color: var(--accent-blue);
    cursor: pointer;
    font-size: 12px;
  }
  .env-link:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .env-list {
    margin: 8px 0 0;
    padding: 0;
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .env-item {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 6px 8px;
    border-radius: 4px;
    background: var(--bg-surface);
    border: 1px solid var(--border-default);
  }
  .env-item strong { color: var(--text-primary); }
  .env-item span { color: var(--text-secondary, var(--text-muted)); }
  .env-hint { color: var(--accent-blue) !important; }
  .status-error { border-color: color-mix(in srgb, var(--accent-red, #c44) 40%, var(--border-default)); }
</style>
