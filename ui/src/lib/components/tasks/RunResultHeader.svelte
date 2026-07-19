<script>
  import { CpuIcon, ClockIcon } from '../../icons.js'

  let { result } = $props()

  let correlationCopied = $state(false)

  async function copyCorrelationId() {
    const cid = result?.correlation_id
    if (!cid || typeof cid !== 'string') return
    try {
      await navigator.clipboard.writeText(cid)
      correlationCopied = true
      setTimeout(() => { correlationCopied = false }, 2000)
    } catch {
      // clipboard unavailable — id remains visible to copy manually
    }
  }
</script>

<div class="result-header">
  <div class="result-meta">
    {#if result.agent}
      <span class="meta-chip">{result.agent}</span>
    {/if}
    {#if result.model}
      <span class="meta-chip model">{result.model}</span>
    {/if}
    {#if result.executor}
      <span class="meta-chip">{result.executor}</span>
    {/if}
    <span class="meta-chip {result.success ? 'ok' : 'err'}">
      {result.success ? 'completed' : 'failed'}
    </span>
    {#if result.dry_run}
      <span class="meta-chip dry" title="all file changes were rolled back">dry-run</span>
    {/if}
    {#if result.safety_violation}
      <span class="meta-chip err" title={result.safety_violation}>safety</span>
    {/if}
    {#if result.billing_fallback}
      <span class="meta-chip warn" title="billing fallback">→ {result.billing_fallback}</span>
    {/if}
    {#if result.correlation_id}
      <button
        type="button"
        class="meta-chip correlation"
        title={correlationCopied ? 'Copied' : 'Copy correlation id for Workers Logs'}
        onclick={copyCorrelationId}
      >
        {correlationCopied ? 'copied' : `corr ${result.correlation_id.slice(0, 8)}…`}
      </button>
    {/if}
  </div>
  <div class="result-stats">
    {#if result.duration_ms}
      <span class="stat"><ClockIcon size="11" strokeWidth="2" />{(result.duration_ms/1000).toFixed(2)}s</span>
    {/if}
    {#if result.usage}
      <span class="stat"><CpuIcon size="11" strokeWidth="2" />{result.usage.input_tokens}+{result.usage.output_tokens}</span>
    {/if}
    {#if result.cost_usd}
      <span class="stat">${result.cost_usd.toFixed(4)}</span>
    {/if}
    {#if result.num_turns}
      <span class="stat">{result.num_turns} turns</span>
    {/if}
  </div>
</div>

<style>
  .result-header {
    padding: 8px 10px;
    border-bottom: 1px solid var(--border-muted);
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }

  .result-meta { display: flex; gap: 4px; flex-wrap: wrap; flex: 1; }

  .meta-chip {
    font-size: 10px;
    font-weight: 500;
    padding: 1px 6px;
    border-radius: var(--radius-sm);
    background: var(--bg-surface);
    border: 1px solid var(--border-default);
    color: var(--text-secondary);
  }
  .meta-chip.model { color: var(--accent-purple); border-color: color-mix(in srgb, var(--accent-purple) 30%, transparent); }
  .meta-chip.ok { color: var(--accent-green); border-color: color-mix(in srgb, var(--accent-green) 30%, transparent); }
  .meta-chip.err { color: var(--accent-red); border-color: color-mix(in srgb, var(--accent-red) 30%, transparent); }
  .meta-chip.dry,
  .meta-chip.warn { color: var(--accent-amber); border-color: color-mix(in srgb, var(--accent-amber) 30%, transparent); }
  .meta-chip.correlation {
    cursor: pointer;
    font-family: var(--font-mono, ui-monospace, monospace);
  }
  .meta-chip.correlation:hover { background: var(--bg-surface-hover); }

  .result-stats {
    display: flex;
    gap: 8px;
    align-items: center;
    flex-shrink: 0;
  }

  .stat {
    display: flex;
    align-items: center;
    gap: 3px;
    font-size: 11px;
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
  }
</style>
