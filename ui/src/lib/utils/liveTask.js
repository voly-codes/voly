/** Map an in-flight RunRecord (/api/runs) to a TaskEvent-shaped object for PipelineInspector. */
export function liveTaskFromRun(run) {
  if (!run?.task_id) return null
  const graphNodes = run.graph_nodes ?? []
  const roles = (run.roles?.length ? run.roles : graphNodes.map(node => node.role || node.id)) ?? []
  const done = run.done_roles ?? 0
  const current = run.current_role ?? ''
  const steps = run.step_statuses ?? []
  const stepByRole = Object.fromEntries(
    steps.map(s => [s.role ?? s.id, s.status]),
  )

  const assignments = roles.map((role, i) => {
    const graphNode = graphNodes.find(node => node.role === role || node.id === role) ?? {}
    const doneRole = i < done
    const isCurrent = role === current
    return {
      role,
      tier: graphNode.tier || '',
      model: graphNode.model || '',
      provider: graphNode.provider || '',
      skills: graphNode.skills || [],
      input_tokens: graphNode.input_tokens || 0,
      output_tokens: graphNode.output_tokens || 0,
      cost_usd: graphNode.cost_usd || 0,
      ok: graphNode.status === 'completed' || doneRole,
      cache_hit: !!graphNode.cache_hit,
      mode: graphNode.status || (isCurrent ? 'running' : doneRole ? 'done' : 'pending'),
      mode_reason: isCurrent ? 'in_progress' : doneRole ? 'completed' : 'queued',
      executor: graphNode.executor || null,
      files_touched: graphNode.files_touched || [],
      plan_status: stepByRole[role] ?? (isCurrent ? 'running' : doneRole ? 'done' : null),
      plan_verify_ok: null,
    }
  })

  return {
    task_id: run.task_id,
    status: run.status || 'running',
    agent: roles.length > 1 ? 'a2a-local' : (run.agent || '—'),
    model: roles.length > 1 ? 'multi-agent' : (run.model || '—'),
    provider: roles.length > 1 ? 'a2a-local' : '',
    executor: roles.length > 1 ? 'a2a-local' : (run.executor || ''),
    task_prompt: run.task || '',
    result: null,
    error: run.error || null,
    duration_ms: Math.round((run.elapsed_seconds ?? 0) * 1000),
    cost_usd: 0,
    _mtime: Date.now() / 1000,
    tokens: { input: 0, output: 0, saved_rtk: 0, saved_headroom: 0 },
    gateway: { cache_hit: false, fallback_used: false, dlp_blocked: false },
    skill_ids: [...new Set(graphNodes.flatMap(node => node.skills || []))],
    a2a_dispatched: roles.length > 1,
    a2a_subtask_count: roles.length,
    a2a_agents_used: roles,
    a2a_assignments: assignments,
    _live: true,
    _live_progress: {
      done_roles: done,
      total_roles: run.total_roles ?? roles.length,
      current_role: current,
      age_seconds: run.age_seconds ?? 0,
    },
    workflow: run.workflow || '',
    lap: run.lap ?? 0,
    max_laps: run.max_laps ?? 0,
    active_role: run.active_role || '',
    stop_reason: run.stop_reason || '',
    latest_verdict: run.latest_verdict || '',
    cancel_requested: !!run.cancel_requested,
    timeline: run.timeline ?? [],
    workflow_metrics: run.workflow_metrics ?? {},
    graph_nodes: graphNodes,
    graph_edges: run.graph_edges ?? [],
    live_steps: steps,
  }
}
