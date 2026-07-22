<script>
  import WorkflowTimeline from './WorkflowTimeline.svelte'
  import { layoutAgentGraph } from './agentGraphModel.js'

  let { task } = $props()
  let layout = $derived(layoutAgentGraph(task?.graph_nodes ?? [], task?.graph_edges ?? []))
  let activeRole = $derived(task?.active_role || task?._live_progress?.current_role || '')
  let transition = $derived(task?.timeline?.at(-1) ?? null)

  function activeEdge(edge) {
    if (transition) return edge.from === transition.from && edge.to === transition.to
    const target = layout.nodes.find(node => node.id === edge.to)
    return target?.status === 'running'
  }

  function fmtMs(value) {
    if (!value) return '—'
    return value >= 1000 ? `${(value / 1000).toFixed(1)}s` : `${Math.round(value)}ms`
  }
</script>

<section class="agent-flow">
  <header class="flow-head">
    <div><span class="eyebrow">Live agent graph</span><strong>One run · {layout.nodes.length} agents</strong></div>
    <div class="run-state">
      {#if task?.lap}<span>lap {task.lap}/{task.max_laps || '—'}</span>{/if}
      <span>{task?.latest_verdict || task?.status || 'running'}</span>
    </div>
  </header>

  <div class="viewport">
    <div class="canvas" style:width={`${layout.width}px`} style:height={`${layout.height}px`}>
      <svg viewBox={`0 0 ${layout.width} ${layout.height}`} aria-hidden="true">
        <defs><marker id="flow-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" /></marker></defs>
        {#each layout.edges as edge}
          <path class="connector" class:active={activeEdge(edge)} d={edge.d} marker-end="url(#flow-arrow)" />
        {/each}
      </svg>

      {#each layout.nodes as node (node.id)}
        <article
          class="agent-node status-{node.status || 'pending'}"
          class:active={node.status === 'running' || node.role === activeRole}
          style:left={`${node.x}px`}
          style:top={`${node.y}px`}
        >
          <div class="node-head"><span class="signal"></span><strong>{node.role || node.id}</strong><span class="state">{node.status || 'pending'}</span></div>
          <div class="route">{node.executor || node.provider || 'route pending'}{node.model ? ` / ${node.model.split('/').pop()}` : ''}</div>
          <div class="metrics"><span>{fmtMs(node.duration_ms)}</span><span>${Number(node.cost_usd || 0).toFixed(4)}</span><span>{node.files_touched?.length || 0} files</span></div>
          {#if node.error}<div class="error" title={node.error}>{node.error}</div>{:else if node.files_touched?.length}<div class="files" title={node.files_touched.join('\n')}>{node.files_touched.slice(0, 2).join(', ')}</div>{/if}
        </article>
      {/each}
    </div>
  </div>

  {#if task?.timeline?.length || task?.stop_reason}
    <WorkflowTimeline entries={task.timeline ?? []} stopReason={task.stop_reason ?? ''} />
  {/if}
</section>

<style>
  .agent-flow { flex: 1; min-height: 0; padding: 14px; display: flex; flex-direction: column; gap: 12px; overflow: hidden; }
  .flow-head { display: flex; align-items: end; justify-content: space-between; gap: 12px; }
  .flow-head div:first-child { display: flex; flex-direction: column; gap: 2px; }
  .eyebrow { color: var(--text-muted); font: 9px var(--font-mono); letter-spacing: .08em; text-transform: uppercase; }
  .flow-head strong { color: var(--text-primary); font-size: 13px; }
  .run-state { display: flex; gap: 6px; }
  .run-state span { padding: 2px 7px; border: 1px solid var(--border-default); border-radius: 10px; color: var(--text-secondary); font: 9px var(--font-mono); }
  .viewport { flex: 1; min-height: 230px; overflow: auto; border: 1px solid var(--border-muted); border-radius: var(--radius-md); background: radial-gradient(circle at 1px 1px, var(--border-muted) 1px, transparent 0); background-size: 18px 18px; }
  .canvas { position: relative; min-width: 100%; min-height: 100%; }
  svg { position: absolute; inset: 0; width: 100%; height: 100%; overflow: visible; }
  .connector { fill: none; stroke: var(--border-default); stroke-width: 1.5; marker-end: url(#flow-arrow); transition: stroke .2s, stroke-width .2s; }
  .connector.active { stroke: var(--accent-amber); stroke-width: 2.5; stroke-dasharray: 7 5; animation: signal 1s linear infinite; }
  marker path { fill: var(--border-default); }
  .agent-node { position: absolute; width: 220px; height: 118px; padding: 10px; border: 1px solid var(--border-default); border-radius: var(--radius-md); background: color-mix(in srgb, var(--bg-surface) 96%, transparent); box-shadow: 0 8px 24px color-mix(in srgb, var(--bg-primary) 45%, transparent); display: flex; flex-direction: column; gap: 7px; transition: border-color .2s, transform .2s; }
  .agent-node.active { border-color: var(--accent-amber); transform: translateY(-2px); }
  .agent-node.status-completed, .agent-node.status-verified { border-color: color-mix(in srgb, var(--accent-green) 50%, var(--border-default)); }
  .agent-node.status-failed, .agent-node.status-blocked { border-color: color-mix(in srgb, var(--accent-red) 55%, var(--border-default)); }
  .node-head { display: flex; align-items: center; gap: 6px; min-width: 0; }
  .node-head strong { flex: 1; color: var(--text-primary); font-size: 12px; overflow: hidden; text-overflow: ellipsis; }
  .signal { width: 7px; height: 7px; border-radius: 50%; background: var(--text-muted); }
  .active .signal { background: var(--accent-amber); box-shadow: 0 0 0 4px color-mix(in srgb, var(--accent-amber) 14%, transparent); }
  .status-completed .signal, .status-verified .signal { background: var(--accent-green); }
  .status-failed .signal, .status-blocked .signal { background: var(--accent-red); }
  .state { color: var(--text-muted); font: 9px var(--font-mono); }
  .route, .metrics, .files, .error { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font: 10px var(--font-mono); color: var(--text-secondary); }
  .metrics { display: flex; gap: 10px; color: var(--text-muted); }
  .files { color: var(--accent-blue); }
  .error { color: var(--accent-red); }
  @keyframes signal { to { stroke-dashoffset: -12; } }
  @media (prefers-reduced-motion: reduce) { .connector.active { animation: none; } .agent-node { transition: none; } }
</style>
