<script>
  import { CpuIcon, ClockIcon, BookOpenIcon } from '../../icons.js'

  let { result } = $props()
</script>

<div class="run-result">
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

  {#if result.injected_skills?.length}
    <div class="injected-skills">
      <BookOpenIcon size="11" strokeWidth="2" />
      <span class="injected-label">Skills:</span>
      {#each result.injected_skills as sid}
        <span class="skill-chip">{sid}</span>
      {/each}
    </div>
  {/if}

  {#if result.content}
    <pre class="result-content">{result.content}</pre>
  {/if}

  {#if result.error}
    <div class="result-err-msg">{result.error}</div>
  {/if}
</div>

<style>
  .run-result {
    background: var(--bg-inset);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    overflow: hidden;
  }

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

  .injected-skills {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 4px;
    padding: 6px 10px;
    border-bottom: 1px solid var(--border-muted);
    color: var(--accent-teal);
    font-size: 11px;
  }

  .injected-label {
    font-weight: 500;
    margin-right: 2px;
  }

  .skill-chip {
    font-size: 10px;
    font-family: var(--font-mono);
    background: color-mix(in srgb, var(--accent-teal) 12%, transparent);
    border: 1px solid color-mix(in srgb, var(--accent-teal) 30%, transparent);
    color: var(--accent-teal);
    border-radius: var(--radius-sm);
    padding: 1px 5px;
  }

  .result-content {
    padding: 12px;
    font-size: 12px;
    font-family: var(--font-mono);
    color: var(--text-primary);
    white-space: pre-wrap;
    word-break: break-word;
    max-height: none;
    overflow-y: visible;
    line-height: 1.6;
  }

  .result-err-msg {
    padding: 8px 12px;
    font-size: 12px;
    color: var(--accent-red);
  }
</style>
