<script>
  import StatusDot from '../shared/StatusDot.svelte'
  import { t } from '../../i18n/localeStore.svelte.ts'

  let { task } = $props()

  // One node per a2a role when the task dispatched sub-agents; otherwise a
  // single synthetic node built from the top-level task fields, so the atlas
  // always has at least one spoke to draw.
  let nodes = $derived.by(() => {
    if (task?.a2a_dispatched && task.a2a_assignments?.length) {
      return task.a2a_assignments.map((a, i) => ({
        key: `${a.role ?? 'role'}-${i}`,
        role: a.role ?? `role-${i}`,
        status: a.mode === 'running' ? 'running' : a.mode === 'pending' ? 'pending' : (a.ok ? 'ok' : 'error'),
        tier: a.tier ?? null,
        mode: a.mode ?? null,
        executor: a.mode === 'executor' ? (a.executor ?? null) : null,
        provider: a.provider ?? null,
        model: a.model ?? null,
        planStatus: a.plan_status ?? null,
        filesTouched: a.files_touched ?? [],
        cacheHit: !!a.cache_hit,
        memHits: a.mem_hits ?? 0,
        skills: a.skills ?? [],
        durationMs: a.duration_ms ?? 0,
        costUsd: a.cost_usd ?? 0,
        error: a.error ?? null,
      }))
    }
    if (!task) return []
    const report = task.report ?? {}
    const filesTouched = [
      ...(report.files_created ?? []),
      ...(report.files_changed ?? []),
      ...(report.files_deleted ?? []),
    ]
    return [{
      key: 'single',
      role: task.agent ?? t('sidebar.unknown'),
      status: task.status === 'running' ? 'running' : (task.status === 'completed' ? 'ok' : 'error'),
      tier: null,
      mode: null,
      executor: task.executor ?? null,
      provider: task.provider ?? null,
      model: task.model ?? null,
      planStatus: null,
      filesTouched,
      cacheHit: !!task.gateway?.cache_hit,
      memHits: task.memory_hits ?? 0,
      skills: task.skill_ids ?? [],
      durationMs: task.duration_ms ?? 0,
      costUsd: task.cost_usd ?? 0,
      error: task.error ?? null,
    }]
  })

  let okCount = $derived(nodes.filter(n => n.status === 'ok').length)
  let failedCount = $derived(nodes.filter(n => n.status === 'error').length)

  let selectedKey = $state(null)
  let selectedNode = $derived(nodes.find(n => n.key === selectedKey) ?? null)

  function selectNode(key) {
    selectedKey = selectedKey === key ? null : key
  }

  function statusColor(status) {
    if (status === 'ok') return 'var(--accent-green)'
    if (status === 'error') return 'var(--accent-red)'
    if (status === 'running') return 'var(--accent-amber)'
    return 'var(--text-muted)'
  }

  function fmtMs(ms) {
    if (!ms) return '—'
    return ms >= 1000 ? `${(ms / 1000).toFixed(2)}s` : `${Math.round(ms)}ms`
  }
</script>

<div class="atlas">
  <div class="atlas-summary">
    <div class="atlas-stat">
      <span class="atlas-stat-value">{nodes.length}</span>
      <span class="atlas-stat-label">{t('atlas.roles', { n: nodes.length })}</span>
    </div>
    <div class="atlas-stat">
      <span class="atlas-stat-value ok">{okCount}</span>
      <span class="atlas-stat-label">{t('atlas.ok')}</span>
    </div>
    {#if failedCount > 0}
      <div class="atlas-stat">
        <span class="atlas-stat-value err">{failedCount}</span>
        <span class="atlas-stat-label">{t('atlas.failed')}</span>
      </div>
    {/if}
    <div class="atlas-stat">
      <span class="atlas-stat-value">${(task?.cost_usd ?? 0).toFixed(4)}</span>
      <span class="atlas-stat-label">{t('atlas.totalCost')}</span>
    </div>
    <div class="atlas-stat">
      <span class="atlas-stat-value">{fmtMs(task?.duration_ms)}</span>
      <span class="atlas-stat-label">{t('atlas.totalDuration')}</span>
    </div>
  </div>

  <div class="atlas-graph">
    <div class="atlas-hub-wrap">
      <div class="atlas-node atlas-hub">
        <span class="atlas-hub-label">{t('atlas.task')}</span>
        <span class="atlas-hub-id">{(task?.task_id ?? '').slice(0, 8)}</span>
      </div>
    </div>

    <div class="atlas-branches">
      {#each nodes as n (n.key)}
        <div class="atlas-branch">
          <button
            type="button"
            class="atlas-node atlas-spoke"
            class:selected={selectedKey === n.key}
            onclick={() => selectNode(n.key)}
          >
            <div class="spoke-head">
              <StatusDot status={n.status === 'ok' ? 'completed' : n.status === 'error' ? 'failed' : n.status} size={7} />
              <span class="spoke-role">{n.role}</span>
              {#if n.tier}<span class="spoke-tier tier-{n.tier}">{n.tier}</span>{/if}
            </div>
            <div class="spoke-meta">
              {#if n.executor}
                <span class="spoke-model">{n.executor}</span>
              {:else if n.provider || n.model}
                <span class="spoke-model">{n.provider}{n.model ? `/${n.model.split('/').pop()}` : ''}</span>
              {:else}
                <span class="spoke-model muted">—</span>
              {/if}
            </div>
            <div class="spoke-metrics">
              <span class="spoke-metric">{fmtMs(n.durationMs)}</span>
              <span class="spoke-metric">${n.costUsd.toFixed(4)}</span>
              {#if n.filesTouched.length}
                <span class="spoke-metric files">{n.filesTouched.length} {t('atlas.files')}</span>
              {/if}
              {#if n.cacheHit}<span class="spoke-badge cached">cache</span>{/if}
            </div>
          </button>
        </div>
      {/each}
    </div>
  </div>

  {#if selectedNode}
    {@const n = selectedNode}
    <div class="atlas-detail">
      <div class="detail-head">
        <span class="detail-dot" style="background:{statusColor(n.status)}"></span>
        <span class="detail-role">{n.role}</span>
      </div>

      <div class="detail-columns">
        <div class="detail-col">
          <div class="detail-col-title">{t('atlas.properties')}</div>
          <div class="detail-row"><span class="detail-k">{t('meta.executor')}</span><span class="detail-v">{n.executor ?? '—'}</span></div>
          <div class="detail-row"><span class="detail-k">{t('meta.provider')}</span><span class="detail-v">{n.provider ?? '—'}</span></div>
          <div class="detail-row"><span class="detail-k">{t('meta.model')}</span><span class="detail-v mono">{n.model ?? '—'}</span></div>
          {#if n.tier}<div class="detail-row"><span class="detail-k">Tier</span><span class="detail-v">{n.tier}</span></div>{/if}
          {#if n.mode}<div class="detail-row"><span class="detail-k">{t('inspector.mode')}</span><span class="detail-v">{n.mode}</span></div>{/if}
          {#if n.planStatus}<div class="detail-row"><span class="detail-k">Plan</span><span class="detail-v">{n.planStatus}</span></div>{/if}
        </div>

        <div class="detail-col">
          <div class="detail-col-title">{t('atlas.metrics')}</div>
          <div class="detail-row"><span class="detail-k">{t('cost.duration')}</span><span class="detail-v">{fmtMs(n.durationMs)}</span></div>
          <div class="detail-row"><span class="detail-k">{t('cost.cost')}</span><span class="detail-v">${n.costUsd.toFixed(6)}</span></div>
          <div class="detail-row"><span class="detail-k">{t('inspector.cache')}</span><span class="detail-v" class:ok={n.cacheHit} class:muted={!n.cacheHit}>{n.cacheHit ? t('inspector.cacheHit') : t('inspector.cacheMiss')}</span></div>
          {#if n.memHits}<div class="detail-row"><span class="detail-k">Memory</span><span class="detail-v">{n.memHits}</span></div>{/if}
        </div>
      </div>

      {#if n.filesTouched.length}
        <div class="detail-block">
          <div class="detail-col-title">{t('atlas.filesTouched')}</div>
          <div class="detail-files">
            {#each n.filesTouched as f}<div class="detail-file mono">{f}</div>{/each}
          </div>
        </div>
      {/if}

      <div class="detail-block">
        <div class="detail-col-title">{t('atlas.skills')}</div>
        {#if n.skills.length}
          <div class="detail-skills">
            {#each n.skills as s}<span class="detail-skill">{s}</span>{/each}
          </div>
        {:else}
          <span class="detail-v muted">{t('atlas.noSkills')}</span>
        {/if}
      </div>

      {#if n.error}
        <div class="detail-block">
          <div class="detail-col-title err">{t('atlas.error')}</div>
          <div class="detail-error">{n.error}</div>
        </div>
      {/if}
    </div>
  {:else}
    <div class="atlas-hint">{t('atlas.selectNode')}</div>
  {/if}
</div>

<style>
  .atlas {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .atlas-summary {
    display: flex;
    gap: 18px;
    flex-wrap: wrap;
    padding-bottom: 12px;
    border-bottom: 1px solid var(--border-muted);
  }

  .atlas-stat { display: flex; flex-direction: column; gap: 2px; }
  .atlas-stat-value { font-size: 15px; font-weight: 600; color: var(--text-primary); font-variant-numeric: tabular-nums; }
  .atlas-stat-value.ok { color: var(--accent-green); }
  .atlas-stat-value.err { color: var(--accent-red); }
  .atlas-stat-label { font-size: 10px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.04em; }

  .atlas-graph {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 8px 0 4px;
  }

  .atlas-node {
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md, 8px);
    background: var(--bg-inset);
  }

  .atlas-hub-wrap {
    display: flex;
    justify-content: center;
  }

  .atlas-hub {
    padding: 8px 18px;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    border-style: dashed;
  }

  .atlas-hub-label {
    font-size: 9px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-muted);
  }

  .atlas-hub-id {
    font-size: 11px;
    font-family: var(--font-mono);
    color: var(--text-secondary);
  }

  .atlas-branches {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 14px;
    margin-top: 14px;
  }

  .atlas-branch {
    display: flex;
    flex-direction: column;
    align-items: center;
  }

  .atlas-branch::before {
    content: '';
    width: 1px;
    height: 14px;
    background: var(--border-default);
  }

  .atlas-spoke {
    width: 200px;
    padding: 8px 10px;
    display: flex;
    flex-direction: column;
    gap: 6px;
    text-align: left;
    cursor: pointer;
    transition: border-color 0.12s, background 0.12s;
  }

  .atlas-spoke:hover { border-color: var(--accent-blue); }
  .atlas-spoke.selected { border-color: var(--accent-blue); background: color-mix(in srgb, var(--accent-blue) 6%, var(--bg-inset)); }

  .spoke-head { display: flex; align-items: center; gap: 6px; }
  .spoke-role { font-size: 12px; font-weight: 600; color: var(--text-primary); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  .spoke-tier {
    font-size: 8px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.03em;
    padding: 1px 5px; border-radius: var(--radius-sm); border: 1px solid var(--border-default); color: var(--text-muted);
  }
  .spoke-tier.tier-premium { color: var(--accent-purple); border-color: color-mix(in srgb, var(--accent-purple) 30%, transparent); }
  .spoke-tier.tier-standard { color: var(--accent-teal); border-color: color-mix(in srgb, var(--accent-teal) 30%, transparent); }
  .spoke-tier.tier-cheap { color: var(--accent-amber); border-color: color-mix(in srgb, var(--accent-amber) 30%, transparent); }

  .spoke-meta { font-size: 10px; color: var(--text-muted); }
  .spoke-model { font-family: var(--font-mono); }
  .spoke-model.muted { color: var(--text-muted); }

  .spoke-metrics { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
  .spoke-metric { font-size: 10px; color: var(--text-muted); font-variant-numeric: tabular-nums; }
  .spoke-metric.files { color: var(--accent-orange, #f59e0b); }
  .spoke-badge {
    font-size: 9px; font-weight: 600; padding: 0 5px; border-radius: var(--radius-sm);
    color: var(--accent-green); background: color-mix(in srgb, var(--accent-green) 12%, transparent);
    border: 1px solid color-mix(in srgb, var(--accent-green) 30%, transparent);
  }

  .atlas-hint {
    text-align: center;
    font-size: 11px;
    color: var(--text-muted);
    padding: 4px 0 8px;
  }

  .atlas-detail {
    border-top: 1px solid var(--border-muted);
    padding-top: 12px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .detail-head { display: flex; align-items: center; gap: 7px; }
  .detail-dot { width: 7px; height: 7px; border-radius: 50%; }
  .detail-role { font-size: 13px; font-weight: 600; color: var(--text-primary); }

  .detail-columns { display: flex; gap: 24px; flex-wrap: wrap; }
  .detail-col { display: flex; flex-direction: column; gap: 4px; min-width: 200px; }
  .detail-col-title {
    font-size: 9px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em;
    color: var(--text-muted); margin-bottom: 2px;
  }
  .detail-col-title.err { color: var(--accent-red); }

  .detail-row { display: flex; align-items: baseline; gap: 8px; font-size: 11px; }
  .detail-k { width: 90px; flex-shrink: 0; color: var(--text-muted); font-size: 10px; }
  .detail-v { color: var(--text-secondary); font-variant-numeric: tabular-nums; }
  .detail-v.mono { font-family: var(--font-mono); font-size: 10px; word-break: break-all; }
  .detail-v.ok { color: var(--accent-green); }
  .detail-v.muted { color: var(--text-muted); }

  .detail-block { display: flex; flex-direction: column; gap: 4px; }

  .detail-files { display: flex; flex-direction: column; gap: 2px; max-height: 160px; overflow-y: auto; }
  .detail-file { font-size: 10px; color: var(--text-secondary); }
  .detail-file.mono { font-family: var(--font-mono); }

  .detail-skills { display: flex; gap: 4px; flex-wrap: wrap; }
  .detail-skill {
    font-size: 9px; font-family: var(--font-mono); border-radius: var(--radius-sm); padding: 1px 6px;
    background: color-mix(in srgb, var(--accent-teal) 12%, transparent);
    border: 1px solid color-mix(in srgb, var(--accent-teal) 30%, transparent); color: var(--accent-teal);
  }

  .detail-error {
    font-size: 11px;
    color: var(--accent-red);
    background: color-mix(in srgb, var(--accent-red) 8%, transparent);
    border-radius: var(--radius-sm);
    padding: 6px 8px;
    font-family: var(--font-mono);
    white-space: pre-wrap;
    word-break: break-word;
  }
</style>
