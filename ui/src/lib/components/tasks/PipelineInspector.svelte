<script>
  import {
    RouteIcon, DatabaseIcon, ZapIcon, LayersIcon,
    BrainCircuitIcon, MessageSquareIcon, SaveIcon,
    BarChart2Icon, BookOpenIcon,
  } from '../../icons.js'
  import { statusRu, calcPct } from '../../utils/format.js'
  import { i18n, t } from '../../i18n/localeStore.svelte.ts'
  import { tasksStore } from '../../stores/tasksStore.svelte'
  import PipelineEmptyState from './PipelineEmptyState.svelte'
  import TaskHeader from './TaskHeader.svelte'
  import PipelineStages from './PipelineStages.svelte'
  import StatsOverview from './StatsOverview.svelte'
  import WorkReport from './WorkReport.svelte'
  import ExtrasSection from './ExtrasSection.svelte'
  import PxpipeArtifacts from './PxpipeArtifacts.svelte'

  let outputExpanded = $state(true)
  let task = $derived(tasksStore.selected)

  // Token flow bar segments
  let tokenBar = $derived.by(() => {
    void i18n.locale
    if (!task) return []
    const tokens = task.tokens ?? {}
    const rtkSaved  = tokens.saved_rtk ?? 0
    const hrSaved   = tokens.saved_headroom ?? 0
    const input     = tokens.input ?? 0
    const output    = tokens.output ?? 0
    const total = rtkSaved + hrSaved + input + output
    if (!total) return []
    const seg = (n) => Math.round((n / total) * 100)
    return [
      { label: 'RTK',     value: rtkSaved, pct: seg(rtkSaved), color: 'var(--accent-teal)' },
      { label: 'Headroom',value: hrSaved,  pct: seg(hrSaved),  color: 'var(--accent-purple)' },
      { label: t('tokens.input'),  value: input,  pct: seg(input),  color: 'var(--accent-blue)' },
      { label: t('tokens.output'), value: output, pct: seg(output), color: 'var(--accent-indigo)' },
    ].filter(s => s.value > 0)
  })

  let stages = $derived.by(() => {
    void i18n.locale
    if (!task) return []
    const tk = task
    const tokens = tk.tokens ?? {}
    const gw = tk.gateway ?? {}
    const totalIn = tokens.input ?? 0
    const savedRtk = tokens.saved_rtk ?? 0
    const savedHr = tokens.saved_headroom ?? 0

    return [
      {
        id: 'route', label: t('stage.route'),
        hint: t('stage.route.hint'),
        icon: RouteIcon, detail: `${tk.agent} → ${tk.model}`, meta: tk.provider ?? '',
        badge: tk.routing_score ? `score ${(tk.routing_score * 100).toFixed(0)}%` : null, ok: true,
      },
      {
        id: 'memory', label: t('stage.memory'),
        hint: t('stage.memory.hint'),
        icon: DatabaseIcon,
        detail: tk.memory_hits ? t('stage.memory.hits', { n: tk.memory_hits }) : t('stage.memory.none'),
        meta: '', badge: tk.memory_hits ? `+${tk.memory_hits}` : null,
        badgeColor: tk.memory_hits ? 'var(--accent-blue)' : null, ok: true,
      },
      {
        id: 'rtk', label: t('stage.rtk'),
        hint: t('stage.rtk.hint'),
        icon: ZapIcon,
        detail: savedRtk ? t('stage.rtk.saved', { n: savedRtk.toLocaleString() }) : t('stage.rtk.none'),
        meta: savedRtk ? t('stage.reduction', { n: calcPct(savedRtk, totalIn) }) : '',
        badge: savedRtk ? `-${savedRtk.toLocaleString()}` : null,
        badgeColor: savedRtk ? 'var(--accent-teal)' : null, ok: true,
      },
      {
        id: 'skill_inject', label: t('stage.skills'),
        hint: t('stage.skills.hint'),
        icon: BookOpenIcon,
        detail: tk.skill_ids?.length
          ? t('stage.skills.injected', { n: tk.skill_ids.length })
          : t('stage.skills.none'),
        meta: tk.skill_ids?.join(', ') ?? '',
        badge: tk.skill_ids?.length ? `+${tk.skill_ids.length}` : null,
        badgeColor: tk.skill_ids?.length ? 'var(--accent-teal)' : null, ok: true,
      },
      {
        id: 'headroom', label: t('stage.headroom'),
        hint: t('stage.headroom.hint'),
        icon: LayersIcon,
        detail: savedHr ? t('stage.headroom.saved', { n: savedHr.toLocaleString() }) : t('stage.headroom.none'),
        meta: savedHr ? t('stage.reduction', { n: calcPct(savedHr, totalIn) }) : '',
        badge: savedHr ? `-${savedHr.toLocaleString()}` : null,
        badgeColor: savedHr ? 'var(--accent-purple)' : null, ok: true,
      },
      ...(tk.dspy_enabled ? [{
        id: 'dspy', label: t('stage.dspy'),
        hint: t('stage.dspy.hint'),
        icon: BrainCircuitIcon, detail: tk.dspy_program_id ?? t('stage.dspy.enabled'),
        meta: t('stage.dspy.meta', { mode: tk.dspy_mode ?? 'shadow', tag: tk.dspy_program_tag ?? '—' }),
        badge: tk.dspy_mode, ok: true,
      }] : []),
      {
        id: 'model_call', label: t('stage.model'),
        hint: t('stage.model.hint'),
        icon: MessageSquareIcon,
        detail: t('stage.model.tokens', {
          in: totalIn.toLocaleString(),
          out: (tokens.output ?? 0).toLocaleString(),
        }),
        meta: [
          gw.cache_hit ? t('stage.model.cacheHit') : null,
          gw.fallback_used ? `fallback → ${gw.fallback_model || '?'}` : null,
          gw.dlp_blocked ? t('stage.model.dlpBlocked') : null,
        ].filter(Boolean).join(' · ') || `${tk.provider ?? ''}`,
        badge: gw.cache_hit ? t('stage.model.cacheBadge') : (gw.fallback_used ? 'fallback' : null),
        badgeColor: gw.cache_hit ? 'var(--accent-green)' : (gw.fallback_used ? 'var(--accent-amber)' : null),
        ok: !gw.dlp_blocked,
      },
      {
        id: 'memory_store', label: t('stage.store'),
        hint: t('stage.store.hint'),
        icon: SaveIcon,
        detail: tk.status === 'completed' ? t('stage.store.saved') : t('stage.store.skipped'),
        ok: tk.status === 'completed',
      },
      {
        id: 'telemetry', label: t('stage.telemetry'),
        hint: t('stage.telemetry.hint'),
        icon: BarChart2Icon,
        detail: tk.duration_ms
          ? t('stage.telemetry.total', { s: (tk.duration_ms / 1000).toFixed(2) })
          : '—',
        meta: t('stage.telemetry.status', { s: statusRu[tk.status] ?? tk.status }),
        ok: tk.status === 'completed',
      },
    ]
  })
</script>

{#if !task}
  <PipelineEmptyState />
{:else}
  <div class="inspector">
    <TaskHeader {task} />

    <div class="inspector-body">
      <div class="left-pane">
        <PipelineStages {stages} />
      </div>

      <div class="right-pane">
        {#if task.task_prompt}
          <div class="task-prompt-field">
            <span class="task-prompt-label">{t('inspector.task')}</span>
            <div class="task-prompt-text">{task.task_prompt}</div>
          </div>
        {/if}

        <StatsOverview
          costUsd={task.cost_usd ?? 0}
          inputTokens={task.tokens?.input ?? 0}
          outputTokens={task.tokens?.output ?? 0}
          savedTokens={(task.tokens?.saved_rtk ?? 0) + (task.tokens?.saved_headroom ?? 0)}
          durationMs={task.duration_ms}
          routingScore={task.routing_score}
          {tokenBar}
        />

        <WorkReport report={task.report} />
        <PxpipeArtifacts artifacts={task.artifacts} />

        <div class="right-sections">
          {#if task.result}
            <ExtrasSection title={t("inspector.output")} chip="{(task.tokens?.output ?? 0).toLocaleString()} tok" collapsible bind:expanded={outputExpanded}>
              <div class="text-block output-block">{task.result}</div>
            </ExtrasSection>
          {/if}

          {#if task.a2a_dispatched && task.a2a_assignments?.length}
            <ExtrasSection title={t("inspector.multiAgents")} chip="{task.a2a_assignments.length} {t('inspector.roles', { n: task.a2a_assignments.length })}">
              <div class="agents-list">
                {#each task.a2a_assignments as a}
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
                    {#if (a.cost_usd ?? 0) > 0 || !task._live}
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

          {#if task.gateway}
            {@const gw = task.gateway}
            <ExtrasSection title={t("inspector.gateway")}>
              <div class="extras-grid">
                <div class="extra-row"><span class="extra-k">{t('inspector.cache')}</span><span class="extra-v" class:ok={gw.cache_hit} class:muted={!gw.cache_hit}>{gw.cache_hit ? t('inspector.cacheHit') : t('inspector.cacheMiss')}</span></div>
                <div class="extra-row">
                  <span class="extra-k">{t('inspector.fallback')}</span>
                  <span class="extra-v" class:warn={gw.fallback_used} class:muted={!gw.fallback_used}>
                    {#if gw.fallback_used}
                      {t('inspector.fallbackUsed')} {gw.fallback_model || '?'}{gw.fallback_provider ? ` (${gw.fallback_provider})` : ''}
                    {:else}
                      {t('inspector.fallbackNotNeeded')}
                    {/if}
                  </span>
                </div>
                {#if gw.fallback_used && gw.fallback_reason}
                  <div class="extra-row fallback-reason-row">
                    <span class="extra-k">{t('inspector.reason')}</span>
                    <span class="extra-v err fallback-reason" title={gw.fallback_reason}>{gw.fallback_reason}</span>
                  </div>
                {/if}
                <div class="extra-row"><span class="extra-k">DLP</span><span class="extra-v" class:err={gw.dlp_blocked} class:muted={!gw.dlp_blocked}>{gw.dlp_blocked ? t('inspector.dlpBlocked') : t('inspector.dlpPassed')}</span></div>
                {#if task.provider}
                  <div class="extra-row"><span class="extra-k">{t('inspector.provider')}</span><span class="extra-v">{task.provider}</span></div>
                {/if}
              </div>
            </ExtrasSection>
          {/if}

          {#if task.chain_timelog?.length > 1}
            {@const STATUS_COLOR = {success:'var(--accent-green)',billing_error:'var(--accent-red)',not_available:'var(--accent-amber)',skipped:'var(--text-muted)',failed:'var(--accent-red)'}}
            {@const STATUS_LABEL = {success:'✓ success',billing_error:'billing error',not_available:'not available',skipped:'skipped',failed:'failed'}}
            <ExtrasSection title="Billing Chain">
              <div class="chain-timeline">
                {#each task.chain_timelog as entry, i}
                  <div class="chain-tl-row">
                    <div class="chain-tl-dot" style="background:{STATUS_COLOR[entry.status] ?? 'var(--text-muted)'}"></div>
                    <div class="chain-tl-line-wrap">
                      {#if i < task.chain_timelog.length - 1}
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

          {#if task.dspy_enabled}
            <ExtrasSection title="DSPy">
              <div class="extras-grid">
                <div class="extra-row"><span class="extra-k">{t('inspector.mode')}</span><span class="extra-v">{task.dspy_mode ?? '—'}</span></div>
                {#if task.dspy_program_id}<div class="extra-row"><span class="extra-k">{t('inspector.program')}</span><span class="extra-v mono">{task.dspy_program_id}</span></div>{/if}
                {#if task.dspy_program_version}<div class="extra-row"><span class="extra-k">{t('inspector.version')}</span><span class="extra-v">v{task.dspy_program_version}</span></div>{/if}
                {#if task.dspy_program_tag}<div class="extra-row"><span class="extra-k">{t('inspector.tag')}</span><span class="extra-v">{task.dspy_program_tag}</span></div>{/if}
                {#if task.dspy_score != null}<div class="extra-row"><span class="extra-k">Score</span><span class="extra-v ok">{(task.dspy_score * 100).toFixed(1)}%</span></div>{/if}
                {#if task.dspy_shadow_delta != null}<div class="extra-row"><span class="extra-k">Shadow delta</span><span class="extra-v">{task.dspy_shadow_delta > 0 ? '+' : ''}{task.dspy_shadow_delta.toFixed(3)}</span></div>{/if}
              </div>
            </ExtrasSection>
          {/if}

          <ExtrasSection title={t('inspector.metadata')}>
            <div class="extras-grid">
              <div class="extra-row"><span class="extra-k">Task ID</span><span class="extra-v mono">{task.task_id}</span></div>
              {#if task.task_type}<div class="extra-row"><span class="extra-k">{t('inspector.type')}</span><span class="extra-v">{task.task_type}</span></div>{/if}
              {#if task.routing_score}<div class="extra-row"><span class="extra-k">Routing</span><span class="extra-v">{(task.routing_score * 100).toFixed(1)}%</span></div>{/if}
              {#if task.automation_score}<div class="extra-row"><span class="extra-k">{t('inspector.automation')}</span><span class="extra-v">{(task.automation_score * 100).toFixed(0)}%</span></div>{/if}
              {#if task.manual_steps_removed}<div class="extra-row"><span class="extra-k">{t('inspector.stepsRemoved')}</span><span class="extra-v ok">{task.manual_steps_removed}</span></div>{/if}
              {#if task.skill_ids?.length}<div class="extra-row"><span class="extra-k">{t('inspector.skills')}</span><span class="extra-v mono">{task.skill_ids.join(', ')}</span></div>{/if}
            </div>
          </ExtrasSection>
        </div>
      </div>
    </div>
  </div>
{/if}

<style>
  .inspector {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .inspector-body {
    flex: 1;
    display: flex;
    overflow: hidden;
  }

  .left-pane {
    flex: 1;
    min-width: 0;
    border-right: 1px solid var(--border-default);
    overflow-y: auto;
    padding: 14px 14px 14px 16px;
    display: flex;
    flex-direction: column;
  }

  .right-pane {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .right-sections {
    flex: 1;
    overflow-y: auto;
    padding: 0 16px 16px;
  }

  .task-prompt-field {
    padding: 10px 14px 8px;
    border-bottom: 1px solid var(--border-default);
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    gap: 5px;
  }

  .task-prompt-label {
    font-size: 9px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-muted);
  }

  .task-prompt-text {
    font-size: 12px;
    color: var(--text-primary);
    line-height: 1.5;
    white-space: pre-wrap;
    word-break: break-word;
    max-height: 120px;
    overflow-y: auto;
    background: var(--bg-inset);
    border: 1px solid var(--border-muted);
    border-radius: var(--radius-sm);
    padding: 6px 8px;
  }

  .extras-grid { display: flex; flex-direction: column; gap: 3px; }

  /* Multi-agent assignments */
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

  .extra-row {
    display: flex;
    align-items: baseline;
    gap: 8px;
    font-size: 11px;
  }

  .extra-k {
    width: 110px;
    flex-shrink: 0;
    color: var(--text-muted);
    font-size: 10px;
  }

  .extra-v {
    color: var(--text-secondary);
    font-variant-numeric: tabular-nums;
  }

  .extra-v.mono { font-family: var(--font-mono); font-size: 10px; word-break: break-all; }
  .extra-v.ok   { color: var(--accent-green); }
  .extra-v.warn { color: var(--accent-amber); }
  .extra-v.err  { color: var(--accent-red); }
  .extra-v.muted { color: var(--text-muted); }

  .fallback-reason {
    font-size: 10px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 200px;
    cursor: help;
  }

  /* Billing chain timeline */
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

  .text-block {
    margin-top: 7px;
    font-size: 11px;
    color: var(--text-secondary);
    line-height: 1.55;
    white-space: pre-wrap;
    word-break: break-word;
    background: var(--bg-inset);
    border-radius: var(--radius-sm);
    padding: 8px 10px;
    border: 1px solid var(--border-muted);
    max-height: 200px;
    overflow-y: auto;
  }

  .output-block {
    font-family: var(--font-mono);
    font-size: 10.5px;
    max-height: 300px;
  }
</style>
