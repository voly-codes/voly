<script>
  import WorkflowTimeline from './WorkflowTimeline.svelte'

  let { task, compact = false } = $props()

  let laps = $derived(task?.laps ?? [])
  let currentLap = $derived(task?.lap ?? laps.length)
  let maxLaps = $derived(task?.max_laps ?? laps.length)
  let activeRole = $derived(task?.active_role ?? '')
  let stopReason = $derived(task?.stop_reason ?? '')
  let verdict = $derived(task?.latest_verdict ?? laps.at(-1)?.verdict ?? '')
  let cost = $derived(task?.total_cost_usd ?? task?.cost_usd ?? 0)
  let duration = $derived(task?.duration_ms ?? 0)

  let timeline = $derived.by(() => {
    if (task?.timeline?.length) return task.timeline
    const entries = []
    for (const lap of laps) {
      entries.push({ lap: lap.number, from: lap.number === 1 ? 'start' : 'reviewer', to: 'developer', reason: lap.number === 1 ? 'initial_task' : 'blocking_findings' })
      if (lap.reviewer_model || lap.verdict) entries.push({ lap: lap.number, from: 'developer', to: 'reviewer', reason: 'implementation_ready' })
    }
    return entries
  })

  function roleStats(role) {
    const relevant = laps.filter(l => role === 'developer' ? l.developer_executor : (l.reviewer_model || l.verdict))
    return {
      executor: role === 'developer' ? relevant.at(-1)?.developer_executor : '',
      provider: role === 'reviewer' ? relevant.at(-1)?.reviewer_provider : '',
      model: role === 'reviewer' ? relevant.at(-1)?.reviewer_model : '',
      duration: relevant.reduce((sum, l) => sum + (role === 'developer' ? (l.developer_duration_ms ?? 0) : (l.reviewer_duration_ms ?? 0)), 0),
      cost: relevant.reduce((sum, l) => sum + (role === 'developer' ? (l.developer_cost_usd ?? 0) : (l.reviewer_cost_usd ?? 0)), 0),
      files: [...new Set(relevant.flatMap(l => l.files_touched ?? []))],
      error: relevant.findLast(l => l.error)?.error ?? '',
    }
  }

  let developer = $derived(roleStats('developer'))
  let reviewer = $derived(roleStats('reviewer'))
  let isRepair = $derived(activeRole === 'developer' && currentLap > 1)

  function fmtMs(ms) {
    if (!ms) return '—'
    return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`
  }
</script>

<section class:compact class="workflow">
  <div class="summary">
    <span class="name">Review until clean</span>
    <span class="chip">lap {currentLap || 0}/{maxLaps || '—'}</span>
    <span class="chip" class:clean={verdict === 'clean'} class:blocking={verdict === 'blocking'}>{verdict || (activeRole ? 'running' : 'waiting')}</span>
    {#if stopReason}<span class="chip stop">{stopReason}</span>{/if}
    <span class="metric">{fmtMs(duration)} · ${Number(cost).toFixed(4)}</span>
  </div>

  <div class="graph">
    <article class="node" class:active={activeRole === 'developer'} class:failed={!!developer.error}>
      <div class="node-head"><span class="dot"></span><strong>Developer</strong><span>{activeRole === 'developer' ? (isRepair ? 'repairing' : 'working') : 'idle'}</span></div>
      <div class="route">{developer.executor || 'executor pending'}</div>
      <div class="metrics">{fmtMs(developer.duration)} · ${developer.cost.toFixed(4)} · {developer.files.length} files</div>
      {#if developer.files.length}<div class="files" title={developer.files.join('\n')}>{developer.files.slice(0, 3).join(', ')}</div>{/if}
      {#if developer.error}<div class="error">{developer.error}</div>{/if}
    </article>

    <div class="edges">
      <div class="edge" class:active={activeRole === 'reviewer'}>implementation <span>→</span></div>
      <div class="edge reverse" class:active={isRepair}><span>←</span> blocking findings</div>
    </div>

    <article class="node" class:active={activeRole === 'reviewer'} class:verified={verdict === 'clean'} class:failed={!!reviewer.error}>
      <div class="node-head"><span class="dot"></span><strong>Reviewer</strong><span>{verdict === 'clean' ? 'verified' : activeRole === 'reviewer' ? 'reviewing' : verdict || 'waiting'}</span></div>
      <div class="route">{reviewer.provider || 'provider pending'}{reviewer.model ? `/${reviewer.model}` : ''}</div>
      <div class="metrics">{fmtMs(reviewer.duration)} · ${reviewer.cost.toFixed(4)}</div>
      {#if reviewer.error}<div class="error">{reviewer.error}</div>{/if}
    </article>
  </div>

  <WorkflowTimeline entries={timeline} {stopReason} />
</section>

<style>
  .workflow { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 16px; background-image: conic-gradient(from 90deg at 2px 2px, color-mix(in srgb, var(--voly-orange) 10%, transparent) 25%, transparent 0); background-size: 18px 18px; }
  .workflow.compact { padding: 10px; border-bottom: 1px solid var(--border-muted); overflow: visible; }
  .summary { display: flex; align-items: center; flex-wrap: wrap; gap: 7px; }
  .name { font: 600 12px var(--font-mono); text-transform: uppercase; color: var(--voly-orange); margin-right: 4px; }
  .chip { padding: 2px 7px; border: 1px solid var(--border-default); border-radius: 2px; color: var(--text-secondary); font: 10px var(--font-mono); }
  .chip.clean { color: var(--accent-green); border-color: color-mix(in srgb, var(--accent-green) 40%, transparent); }
  .chip.blocking, .chip.stop { color: var(--accent-amber); }
  .metric { margin-left: auto; color: var(--text-muted); font: 10px var(--font-mono); }
  .graph { display: grid; grid-template-columns: minmax(180px, 1fr) 130px minmax(180px, 1fr); gap: 12px; align-items: center; }
  .node { min-width: 0; padding: 10px; border: 2px solid color-mix(in srgb, var(--voly-ink) 45%, var(--border-default)); border-radius: 2px; background: color-mix(in srgb, var(--voly-paper) 8%, var(--bg-surface)); box-shadow: 3px 3px 0 color-mix(in srgb, var(--voly-ink) 25%, transparent); display: flex; flex-direction: column; gap: 6px; }
  .node.active { border-color: var(--voly-orange); box-shadow: 5px 5px 0 color-mix(in srgb, var(--voly-orange) 70%, transparent); }
  .node.verified { border-color: var(--accent-green); }
  .node.failed { border-color: var(--accent-red); }
  .node-head { display: flex; align-items: center; gap: 6px; font-size: 10px; color: var(--text-muted); }
  .node-head strong { flex: 1; font: 600 12px var(--font-mono); text-transform: uppercase; color: var(--text-primary); }
  .dot { width: 7px; height: 7px; border-radius: 0; background: var(--text-muted); }
  .active .dot { background: var(--voly-orange); } .verified .dot { background: var(--accent-green); } .failed .dot { background: var(--accent-red); }
  .route, .metrics, .files { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font: 10px var(--font-mono); color: var(--text-secondary); }
  .metrics, .files { color: var(--text-muted); }
  .error { color: var(--accent-red); font-size: 10px; word-break: break-word; }
  .edges { display: flex; flex-direction: column; gap: 10px; }
  .edge { display: flex; justify-content: flex-end; gap: 5px; color: var(--text-muted); font-size: 9px; border-bottom: 1px solid var(--border-default); padding-bottom: 2px; }
  .edge.reverse { justify-content: flex-start; border-bottom: 0; border-top: 1px solid var(--border-default); padding: 2px 0 0; }
  .edge.active { color: var(--voly-orange); border-color: var(--voly-orange); border-style: dashed; font-weight: 600; }
  @media (max-width: 760px) { .graph { grid-template-columns: 1fr; } .edges { transform: rotate(90deg); width: 90px; justify-self: center; } .metric { margin-left: 0; } }
</style>
