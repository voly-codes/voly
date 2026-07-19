<script>
  import ExtrasSection from './ExtrasSection.svelte'

  let { chain_timelog = [] } = $props()

  const STATUS_COLOR = {
    success: 'var(--accent-green)',
    billing_error: 'var(--accent-red)',
    not_available: 'var(--accent-amber)',
    skipped: 'var(--text-muted)',
    failed: 'var(--accent-red)',
  }
  const STATUS_LABEL = {
    success: '✓ success',
    billing_error: 'billing error',
    not_available: 'not available',
    skipped: 'skipped',
    failed: 'failed',
  }
</script>

{#if chain_timelog?.length > 1}
  <ExtrasSection title="Billing Chain">
    <div class="chain-timeline">
      {#each chain_timelog as entry, i}
        <div class="chain-tl-row">
          <div class="chain-tl-dot" style="background:{STATUS_COLOR[entry.status] ?? 'var(--text-muted)'}"></div>
          <div class="chain-tl-line-wrap">
            {#if i < chain_timelog.length - 1}
              <div class="chain-tl-line"></div>
            {/if}
          </div>
          <div class="chain-tl-body">
            <div class="chain-tl-head">
              <span class="chain-tl-executor">{entry.executor}</span>
              {#if entry.model}
                <span class="chain-tl-model">{entry.model.split('/').pop()}</span>
              {/if}
              <span class="chain-tl-status" style="color:{STATUS_COLOR[entry.status] ?? 'var(--text-muted)'}">
                {STATUS_LABEL[entry.status] ?? entry.status}
              </span>
              {#if entry.duration_ms > 0}
                <span class="chain-tl-ms">{(entry.duration_ms/1000).toFixed(2)}s</span>
              {/if}
            </div>
            {#if entry.error && entry.status !== 'success'}
              <div class="chain-tl-error" title={entry.error}>{entry.error.slice(0, 100)}{entry.error.length > 100 ? '…' : ''}</div>
            {/if}
          </div>
        </div>
      {/each}
    </div>
  </ExtrasSection>
{/if}

<style>
  .chain-timeline { display: flex; flex-direction: column; gap: 0; }

  .chain-tl-row {
    display: flex;
    align-items: flex-start;
    gap: 8px;
  }

  .chain-tl-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
    margin-top: 3px;
  }

  .chain-tl-line-wrap {
    width: 8px;
    flex-shrink: 0;
    display: flex;
    justify-content: center;
    padding-top: 4px;
  }

  .chain-tl-line {
    width: 1px;
    height: 100%;
    min-height: 14px;
    background: var(--border-default);
  }

  .chain-tl-body {
    flex: 1;
    padding-bottom: 10px;
  }

  .chain-tl-head {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
  }

  .chain-tl-executor {
    font-size: 11px;
    font-weight: 600;
    font-family: var(--font-mono);
    color: var(--text-primary);
  }

  .chain-tl-model {
    font-size: 10px;
    font-family: var(--font-mono);
    color: var(--text-muted);
    background: var(--bg-inset);
    border: 1px solid var(--border-muted);
    border-radius: var(--radius-sm);
    padding: 0 4px;
  }

  .chain-tl-status {
    font-size: 10px;
    font-weight: 500;
  }

  .chain-tl-ms {
    font-size: 10px;
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
  }

  .chain-tl-error {
    margin-top: 2px;
    font-size: 10px;
    color: var(--accent-red);
    font-family: var(--font-mono);
    opacity: 0.85;
    cursor: help;
    line-height: 1.4;
  }
</style>
