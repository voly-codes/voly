<script>
  import { LayersIcon } from '../../icons.js'

  let { assignments = [], hybrid = null } = $props()

  let hybridSummary = $derived(
    hybrid && (hybrid.executor_roles || hybrid.chat_roles) ? hybrid : null
  )
</script>

{#if assignments?.length}
  <div class="agents-panel">
    <div class="agents-header">
      <LayersIcon size="11" strokeWidth="2" />
      <span>Multi-agent · {assignments.length} agents</span>
    </div>
    <div class="agents-list">
      {#each assignments as a}
        <div class="agent-row">
          <div class="agent-dot" style="background:{a.ok ? 'var(--accent-green)' : 'var(--accent-red)'}"></div>
          <span class="agent-role">{a.role}</span>
          <span class="agent-tier tier-{a.tier}">{a.tier}</span>
          {#if a.mode}
            <span class="agent-badge mode-{a.mode}">{a.mode}</span>
          {/if}
          {#if a.plan_status}
            <span
              class="agent-badge plan-status plan-{a.plan_status}"
              title={a.plan_verify_ok === false ? 'acceptance failed' : `plan: ${a.plan_status}`}
            >{a.plan_status}</span>
          {/if}
          {#if a.mode === 'executor' && a.executor}
            <span class="agent-model">{a.executor}</span>
          {:else}
            <span class="agent-model">{a.provider}/{a.model?.split('/').pop()}</span>
          {/if}
          {#if a.files_touched?.length}
            <span class="agent-badge files" title={a.files_touched.join('\n')}>{a.files_touched.length} files</span>
          {/if}
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

{#if hybridSummary}
  <div class="hybrid-summary">
    <LayersIcon size="11" strokeWidth="2" />
    <span>Hybrid:</span>
    <span class="hy-stat">{hybridSummary.executor_roles ?? 0} executor</span>
    <span class="hy-sep">·</span>
    <span class="hy-stat">{hybridSummary.chat_roles ?? 0} chat</span>
    {#if hybridSummary.files_touched?.length}
      <span class="hy-sep">·</span>
      <span class="hy-stat" title={hybridSummary.files_touched.join('\n')}>
        {hybridSummary.files_touched.length} files
      </span>
    {/if}
  </div>
{/if}

<style>
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
  .agent-badge.mode-executor {
    color: var(--accent-blue, #3b82f6);
    background: color-mix(in srgb, var(--accent-blue, #3b82f6) 12%, transparent);
    border: 1px solid color-mix(in srgb, var(--accent-blue, #3b82f6) 30%, transparent);
  }
  .agent-badge.mode-chat {
    color: var(--text-muted, #94a3b8);
    background: color-mix(in srgb, var(--text-muted, #94a3b8) 10%, transparent);
    border: 1px solid color-mix(in srgb, var(--text-muted, #94a3b8) 25%, transparent);
  }
  .agent-badge.files {
    color: var(--accent-orange, #f59e0b);
    background: color-mix(in srgb, var(--accent-orange, #f59e0b) 12%, transparent);
    border: 1px solid color-mix(in srgb, var(--accent-orange, #f59e0b) 30%, transparent);
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
  .agent-badge.plan-status {
    text-transform: lowercase;
    border: 1px solid var(--border-default);
    color: var(--text-muted);
  }
  .agent-badge.plan-verified {
    color: var(--accent-green);
    border-color: color-mix(in srgb, var(--accent-green) 30%, transparent);
    background: color-mix(in srgb, var(--accent-green) 10%, transparent);
  }
  .agent-badge.plan-failed,
  .agent-badge.plan-blocked {
    color: var(--accent-red);
    border-color: color-mix(in srgb, var(--accent-red) 30%, transparent);
    background: color-mix(in srgb, var(--accent-red) 10%, transparent);
  }
  .agent-badge.plan-running,
  .agent-badge.plan-verifying {
    color: var(--accent-amber, #f59e0b);
    border-color: color-mix(in srgb, var(--accent-amber, #f59e0b) 30%, transparent);
    background: color-mix(in srgb, var(--accent-amber, #f59e0b) 10%, transparent);
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

  .hybrid-summary {
    display: flex;
    align-items: center;
    gap: 5px;
    padding: 6px 10px;
    border-bottom: 1px solid var(--border-muted);
    font-size: 11px;
    color: var(--text-secondary);
  }
  .hy-stat { font-variant-numeric: tabular-nums; }
  .hy-sep { color: var(--text-muted); }
</style>
