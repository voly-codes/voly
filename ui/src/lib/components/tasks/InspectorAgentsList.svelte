<script>
  import { t } from '../../i18n/localeStore.svelte.ts'
  import ExtrasSection from './ExtrasSection.svelte'

  let { assignments = [], live = false } = $props()
</script>

{#if assignments?.length}
  <ExtrasSection title={t("inspector.multiAgents")} chip="{assignments.length} {t('inspector.roles', { n: assignments.length })}">
    <div class="agents-list">
      {#each assignments as a}
        <div class="agent-row">
          <div
            class="agent-dot"
            style="background:{a.mode === 'running' || a.mode === 'pending'
              ? (a.mode === 'running' ? 'var(--accent-amber)' : 'var(--text-muted)')
              : (a.ok ? 'var(--accent-green)' : 'var(--accent-red)')}"
          ></div>
          <span class="agent-role">{a.role}</span>
          {#if a.tier}<span class="agent-tier tier-{a.tier}">{a.tier}</span>{/if}
          {#if a.mode}<span class="agent-badge mode-{a.mode}">{a.mode}</span>{/if}
          {#if a.plan_status}
            <span
              class="agent-badge plan-status plan-{a.plan_status}"
              title={a.plan_verify_ok === false ? 'acceptance failed' : `plan: ${a.plan_status}`}
            >{a.plan_status}</span>
          {/if}
          {#if a.mode === 'executor' && a.executor}
            <span class="agent-model">{a.executor}</span>
          {:else if a.provider || a.model}
            <span class="agent-model">{a.provider}/{a.model?.split('/').pop()}</span>
          {/if}
          {#if a.files_touched?.length}
            <span class="agent-badge files" title={a.files_touched.join('\n')}>{a.files_touched.length} files</span>
          {/if}
          {#if a.cache_hit}<span class="agent-badge cached">cached</span>{/if}
          {#if a.mem_hits}<span class="agent-badge mem">mem {a.mem_hits}</span>{/if}
          <div class="agent-skills">
            {#each a.skills ?? [] as s}<span class="agent-skill">{s}</span>{/each}
          </div>
          {#if (a.duration_ms ?? 0) > 0}
            <span class="agent-duration">{a.duration_ms >= 1000 ? `${Math.round(a.duration_ms / 1000)}s` : `${Math.round(a.duration_ms)}ms`}</span>
          {/if}
          {#if (a.cost_usd ?? 0) > 0 || !live}
            <span class="agent-cost">${(a.cost_usd ?? 0).toFixed(4)}</span>
          {/if}
        </div>
        {#if !a.ok && a.error && a.mode !== 'running' && a.mode !== 'pending'}
          <div class="agent-error" title={a.error}>{a.error}</div>
        {/if}
      {/each}
    </div>
  </ExtrasSection>
{/if}

<style>
  .agents-list { display: flex; flex-direction: column; gap: 5px; }
  .agent-row { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
  .agent-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
  .agent-role { font-size: 11px; font-weight: 600; color: var(--text-secondary); min-width: 66px; }
  .agent-tier {
    font-size: 9px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.03em;
    padding: 1px 5px; border-radius: var(--radius-sm); border: 1px solid var(--border-default); color: var(--text-muted);
  }
  .agent-tier.tier-premium { color: var(--accent-purple); border-color: color-mix(in srgb, var(--accent-purple) 30%, transparent); background: color-mix(in srgb, var(--accent-purple) 10%, transparent); }
  .agent-tier.tier-standard { color: var(--accent-teal); border-color: color-mix(in srgb, var(--accent-teal) 30%, transparent); background: color-mix(in srgb, var(--accent-teal) 10%, transparent); }
  .agent-tier.tier-cheap { color: var(--accent-amber); border-color: color-mix(in srgb, var(--accent-amber) 30%, transparent); background: color-mix(in srgb, var(--accent-amber) 10%, transparent); }
  .agent-model { font-size: 10px; font-family: var(--font-mono); color: var(--text-muted); }
  .agent-badge { font-size: 9px; font-weight: 600; padding: 0 5px; border-radius: var(--radius-sm); }
  .agent-badge.cached { color: var(--accent-green); background: color-mix(in srgb, var(--accent-green) 12%, transparent); border: 1px solid color-mix(in srgb, var(--accent-green) 30%, transparent); }
  .agent-badge.mem { color: var(--accent-purple); background: color-mix(in srgb, var(--accent-purple) 12%, transparent); border: 1px solid color-mix(in srgb, var(--accent-purple) 30%, transparent); }
  .agent-badge.mode-executor { color: var(--accent-blue, #3b82f6); background: color-mix(in srgb, var(--accent-blue, #3b82f6) 12%, transparent); border: 1px solid color-mix(in srgb, var(--accent-blue, #3b82f6) 30%, transparent); }
  .agent-badge.mode-chat { color: var(--text-muted, #94a3b8); background: color-mix(in srgb, var(--text-muted, #94a3b8) 10%, transparent); border: 1px solid color-mix(in srgb, var(--text-muted, #94a3b8) 25%, transparent); }
  .agent-badge.mode-running { color: var(--accent-amber); background: color-mix(in srgb, var(--accent-amber) 12%, transparent); border: 1px solid color-mix(in srgb, var(--accent-amber) 30%, transparent); }
  .agent-badge.mode-pending { color: var(--text-muted); background: color-mix(in srgb, var(--text-muted) 8%, transparent); border: 1px solid var(--border-muted); }
  .agent-badge.mode-done { color: var(--accent-green); background: color-mix(in srgb, var(--accent-green) 12%, transparent); border: 1px solid color-mix(in srgb, var(--accent-green) 30%, transparent); }
  .agent-badge.plan-status { text-transform: lowercase; border: 1px solid var(--border-default); color: var(--text-muted); }
  .agent-badge.plan-verified { color: var(--accent-green); border-color: color-mix(in srgb, var(--accent-green) 30%, transparent); background: color-mix(in srgb, var(--accent-green) 10%, transparent); }
  .agent-badge.plan-failed,
  .agent-badge.plan-blocked { color: var(--accent-red); border-color: color-mix(in srgb, var(--accent-red) 30%, transparent); background: color-mix(in srgb, var(--accent-red) 10%, transparent); }
  .agent-badge.plan-running,
  .agent-badge.plan-verifying { color: var(--accent-amber, #f59e0b); border-color: color-mix(in srgb, var(--accent-amber, #f59e0b) 30%, transparent); background: color-mix(in srgb, var(--accent-amber, #f59e0b) 10%, transparent); }
  .agent-badge.files { color: var(--accent-orange, #f59e0b); background: color-mix(in srgb, var(--accent-orange, #f59e0b) 12%, transparent); border: 1px solid color-mix(in srgb, var(--accent-orange, #f59e0b) 30%, transparent); }
  .agent-skills { display: flex; gap: 3px; flex-wrap: wrap; flex: 1; }
  .agent-skill {
    font-size: 9px; font-family: var(--font-mono); border-radius: var(--radius-sm); padding: 0 5px;
    background: color-mix(in srgb, var(--accent-teal) 12%, transparent);
    border: 1px solid color-mix(in srgb, var(--accent-teal) 30%, transparent); color: var(--accent-teal);
  }
  .agent-cost { font-size: 10px; color: var(--text-muted); font-variant-numeric: tabular-nums; min-width: 52px; text-align: right; }
  .agent-duration { font-size: 10px; color: var(--text-muted); font-family: var(--font-mono); }
  .agent-error {
    margin: 2px 0 4px 14px;
    font-size: 10px;
    color: var(--accent-red);
    background: color-mix(in srgb, var(--accent-red) 8%, transparent);
    border-radius: var(--radius-sm);
    padding: 2px 6px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
</style>
