<script>
  import { LinkIcon } from '../../icons.js'

  let { chain_timelog = [] } = $props()

  const STATUS_COLOR = {
    success:       'var(--accent-green)',
    billing_error: 'var(--accent-red)',
    not_available: 'var(--accent-amber)',
    skipped:       'var(--text-muted)',
    failed:        'var(--accent-red)',
  }
  const STATUS_LABEL = {
    success:       '✓',
    billing_error: 'billing',
    not_available: 'unavail',
    skipped:       'skip',
    failed:        'fail',
  }
</script>

{#if chain_timelog?.length > 1}
  <div class="chain-timelog">
    <div class="chain-header">
      <LinkIcon size="11" strokeWidth="2" />
      <span>Billing chain</span>
    </div>
    <div class="chain-steps">
      {#each chain_timelog as entry, i}
        <div class="chain-step">
          <div class="chain-dot" style="background:{STATUS_COLOR[entry.status] ?? 'var(--text-muted)'}"></div>
          <span class="chain-executor">{entry.executor}</span>
          {#if entry.model}
            <span class="chain-model">{entry.model.split('/').pop()}</span>
          {/if}
          <span class="chain-badge" style="color:{STATUS_COLOR[entry.status] ?? 'var(--text-muted)'}">
            {STATUS_LABEL[entry.status] ?? entry.status}
          </span>
          {#if entry.duration_ms > 0}
            <span class="chain-ms">{(entry.duration_ms/1000).toFixed(1)}s</span>
          {/if}
          {#if i < chain_timelog.length - 1}
            <span class="chain-arrow">→</span>
          {/if}
        </div>
      {/each}
    </div>
  </div>
{/if}

<style>
  .chain-timelog {
    border-bottom: 1px solid var(--border-muted);
    padding: 6px 10px;
  }

  .chain-header {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 9px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-muted);
    margin-bottom: 5px;
  }

  .chain-steps {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 4px;
  }

  .chain-step {
    display: flex;
    align-items: center;
    gap: 3px;
  }

  .chain-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .chain-executor {
    font-size: 10px;
    font-weight: 500;
    color: var(--text-secondary);
    font-family: var(--font-mono);
  }

  .chain-model {
    font-size: 9px;
    color: var(--text-muted);
    font-family: var(--font-mono);
  }

  .chain-badge {
    font-size: 9px;
    font-weight: 600;
  }

  .chain-ms {
    font-size: 9px;
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
  }

  .chain-arrow {
    font-size: 10px;
    color: var(--text-muted);
    margin: 0 1px;
  }
</style>
