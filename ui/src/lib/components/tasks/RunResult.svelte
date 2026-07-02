<script>
  import { CpuIcon, ClockIcon, BookOpenIcon, LinkIcon, LayersIcon } from '../../icons.js'

  let { result } = $props()

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

  {#if result.chain_timelog?.length > 1}
    <div class="chain-timelog">
      <div class="chain-header">
        <LinkIcon size="11" strokeWidth="2" />
        <span>Billing chain</span>
      </div>
      <div class="chain-steps">
        {#each result.chain_timelog as entry, i}
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
            {#if i < result.chain_timelog.length - 1}
              <span class="chain-arrow">→</span>
            {/if}
          </div>
        {/each}
      </div>
    </div>
  {/if}

  {#if result.a2a_dispatched && result.a2a_assignments?.length}
    <div class="agents-panel">
      <div class="agents-header">
        <LayersIcon size="11" strokeWidth="2" />
        <span>Multi-agent · {result.a2a_assignments.length} agents</span>
      </div>
      <div class="agents-list">
        {#each result.a2a_assignments as a}
          <div class="agent-row">
            <div class="agent-dot" style="background:{a.ok ? 'var(--accent-green)' : 'var(--accent-red)'}"></div>
            <span class="agent-role">{a.role}</span>
            <span class="agent-tier tier-{a.tier}">{a.tier}</span>
            <span class="agent-model">{a.provider}/{a.model?.split('/').pop()}</span>
            {#if a.cache_hit}
              <span class="agent-badge cached">cached</span>
            {/if}
            {#if a.mem_hits}
              <span class="agent-badge mem">mem {a.mem_hits}</span>
            {/if}
            <div class="agent-skills">
              {#each a.skills ?? [] as s}
                <span class="agent-skill">{s}</span>
              {/each}
            </div>
            <span class="agent-tokens">{a.input_tokens}+{a.output_tokens}</span>
            {#if a.cost_usd}
              <span class="agent-cost">${a.cost_usd.toFixed(4)}</span>
            {/if}
          </div>
        {/each}
      </div>
    </div>
  {/if}

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

  .agents-panel {
    border-bottom: 1px solid var(--border-muted);
    padding: 6px 10px;
  }

  .agents-header {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 9px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-muted);
    margin-bottom: 6px;
  }

  .agents-list {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .agent-row {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
  }

  .agent-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .agent-role {
    font-size: 11px;
    font-weight: 600;
    color: var(--text-secondary);
    min-width: 68px;
  }

  .agent-tier {
    font-size: 9px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    padding: 1px 5px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-default);
    color: var(--text-muted);
  }
  .agent-tier.tier-premium {
    color: var(--accent-purple);
    border-color: color-mix(in srgb, var(--accent-purple) 30%, transparent);
    background: color-mix(in srgb, var(--accent-purple) 10%, transparent);
  }
  .agent-tier.tier-standard {
    color: var(--accent-teal);
    border-color: color-mix(in srgb, var(--accent-teal) 30%, transparent);
    background: color-mix(in srgb, var(--accent-teal) 10%, transparent);
  }
  .agent-tier.tier-cheap {
    color: var(--accent-amber);
    border-color: color-mix(in srgb, var(--accent-amber) 30%, transparent);
    background: color-mix(in srgb, var(--accent-amber) 10%, transparent);
  }

  .agent-model {
    font-size: 10px;
    font-family: var(--font-mono);
    color: var(--text-muted);
  }

  .agent-badge {
    font-size: 9px;
    font-weight: 600;
    padding: 0 5px;
    border-radius: var(--radius-sm);
  }
  .agent-badge.cached {
    color: var(--accent-green);
    background: color-mix(in srgb, var(--accent-green) 12%, transparent);
    border: 1px solid color-mix(in srgb, var(--accent-green) 30%, transparent);
  }
  .agent-badge.mem {
    color: var(--accent-blue, var(--accent-purple));
    background: color-mix(in srgb, var(--accent-purple) 12%, transparent);
    border: 1px solid color-mix(in srgb, var(--accent-purple) 30%, transparent);
  }

  .agent-skills {
    display: flex;
    gap: 3px;
    flex-wrap: wrap;
    flex: 1;
  }

  .agent-skill {
    font-size: 9px;
    font-family: var(--font-mono);
    background: color-mix(in srgb, var(--accent-teal) 12%, transparent);
    border: 1px solid color-mix(in srgb, var(--accent-teal) 30%, transparent);
    color: var(--accent-teal);
    border-radius: var(--radius-sm);
    padding: 0 5px;
  }

  .agent-tokens {
    font-size: 9px;
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
  }

  .agent-cost {
    font-size: 10px;
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
    min-width: 52px;
    text-align: right;
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
