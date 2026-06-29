<script>
  import {
    RouteIcon, DatabaseIcon, ZapIcon, LayersIcon,
    BrainCircuitIcon, MessageSquareIcon, SaveIcon,
    BarChart2Icon, AlertCircleIcon, CheckCircle2Icon,
    ChevronRightIcon, BookOpenIcon,
  } from '../../icons.js'

  let { task = null } = $props()

  function pct(saved, total) {
    if (!total || !saved) return null
    return Math.round((saved / (total + saved)) * 100)
  }

  let stages = $derived.by(() => {
    if (!task) return []
    const t = task
    const tokens = t.tokens ?? {}
    const gw = t.gateway ?? {}
    const totalIn = tokens.input ?? 0
    const savedRtk = tokens.saved_rtk ?? 0
    const savedHr = tokens.saved_headroom ?? 0

    return [
      {
        id: 'route',
        label: 'Route',
        icon: RouteIcon,
        detail: `${t.agent} → ${t.model}`,
        meta: t.provider ?? '',
        badge: t.routing_score ? `score ${(t.routing_score * 100).toFixed(0)}%` : null,
        ok: true,
      },
      {
        id: 'memory',
        label: 'Memory Retrieve',
        icon: DatabaseIcon,
        detail: t.skill_ids?.length ? `${t.skill_ids.length} skill(s) matched` : 'no hits',
        meta: t.skill_ids?.join(', ') ?? '',
        ok: true,
      },
      {
        id: 'rtk',
        label: 'RTK Filter',
        icon: ZapIcon,
        detail: savedRtk ? `saved ${savedRtk.toLocaleString()} tokens` : 'no savings',
        meta: savedRtk ? `${pct(savedRtk, totalIn)}% reduction` : '',
        badge: savedRtk ? `-${savedRtk.toLocaleString()}` : null,
        badgeColor: savedRtk ? 'var(--accent-teal)' : null,
        ok: true,
      },
      {
        id: 'skill_inject',
        label: 'Skill Inject',
        icon: BookOpenIcon,
        detail: t.injected_skills?.length
          ? `${t.injected_skills.length} skill(s) injected`
          : 'no skills matched',
        meta: t.injected_skills?.join(', ') ?? '',
        badge: t.injected_skills?.length ? `+${t.injected_skills.length}` : null,
        badgeColor: t.injected_skills?.length ? 'var(--accent-teal)' : null,
        ok: true,
      },
      {
        id: 'headroom',
        label: 'Headroom Compress',
        icon: LayersIcon,
        detail: savedHr ? `compressed ${savedHr.toLocaleString()} tokens` : 'no compression',
        meta: savedHr ? `${pct(savedHr, totalIn)}% reduction` : '',
        badge: savedHr ? `-${savedHr.toLocaleString()}` : null,
        badgeColor: savedHr ? 'var(--accent-purple)' : null,
        ok: true,
      },
      ...(t.dspy_enabled ? [{
        id: 'dspy',
        label: 'DSPy Program',
        icon: BrainCircuitIcon,
        detail: t.dspy_program_id ?? 'enabled',
        meta: `mode: ${t.dspy_mode ?? 'shadow'} · tag: ${t.dspy_program_tag ?? '—'}`,
        badge: t.dspy_mode,
        ok: true,
      }] : []),
      {
        id: 'model_call',
        label: 'Model Call',
        icon: MessageSquareIcon,
        detail: `${totalIn.toLocaleString()} in · ${(tokens.output ?? 0).toLocaleString()} out`,
        meta: [
          gw.cache_hit ? 'cache hit' : null,
          gw.fallback_used ? 'fallback used' : null,
          gw.dlp_blocked ? 'DLP blocked' : null,
        ].filter(Boolean).join(' · ') || `${t.provider}`,
        badge: gw.cache_hit ? 'cached' : null,
        badgeColor: gw.cache_hit ? 'var(--accent-green)' : null,
        ok: !gw.dlp_blocked,
      },
      {
        id: 'memory_store',
        label: 'Memory Store',
        icon: SaveIcon,
        detail: t.status === 'completed' ? 'stored to memory' : 'skipped',
        ok: t.status === 'completed',
      },
      {
        id: 'telemetry',
        label: 'Telemetry',
        icon: BarChart2Icon,
        detail: t.duration_ms ? `${(t.duration_ms / 1000).toFixed(2)}s total` : '—',
        meta: `status: ${t.status}`,
        ok: t.status === 'completed',
      },
    ]
  })
</script>

{#if !task}
  <div class="empty-state">
    <ChevronRightIcon size="24" strokeWidth="1.5" />
    <span>Select a task to inspect</span>
  </div>
{:else}
  <div class="inspector">
    <div class="inspector-header">
      <div class="task-title">
        <span class="task-id">{task.task_id?.slice(0, 8)}</span>
        {#if task.workflow}
          <span class="task-workflow">{task.workflow}</span>
        {/if}
        <span class="task-status status-{task.status}">{task.status}</span>
      </div>
      {#if task.error}
        <div class="task-error">
          <AlertCircleIcon size="13" strokeWidth="2" />
          {task.error}
        </div>
      {/if}
    </div>

    <div class="pipeline">
      {#each stages as stage, i (stage.id)}
        <div class="stage" class:stage-error={!stage.ok}>
          <div class="stage-connector">
            <div class="stage-icon" class:stage-icon-ok={stage.ok} class:stage-icon-err={!stage.ok}>
              {#if stage.icon}
                {@const Icon = stage.icon}
                <Icon size="13" strokeWidth="2" />
              {/if}
            </div>
            {#if i < stages.length - 1}
              <div class="stage-line"></div>
            {/if}
          </div>

          <div class="stage-body">
            <div class="stage-top">
              <span class="stage-label">{stage.label}</span>
              {#if stage.badge}
                <span class="stage-badge" style:color={stage.badgeColor ?? 'var(--text-muted)'}>
                  {stage.badge}
                </span>
              {/if}
              {#if stage.ok}
                <CheckCircle2Icon size="11" strokeWidth="2" class="stage-check" />
              {:else}
                <AlertCircleIcon size="11" strokeWidth="2" class="stage-err-icon" />
              {/if}
            </div>
            <div class="stage-detail">{stage.detail}</div>
            {#if stage.meta}
              <div class="stage-meta">{stage.meta}</div>
            {/if}
          </div>
        </div>
      {/each}
    </div>
  </div>
{/if}

<style>
  .empty-state {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 10px;
    color: var(--text-muted);
    font-size: 13px;
  }

  .inspector {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .inspector-header {
    padding: 12px 16px;
    border-bottom: 1px solid var(--border-default);
    flex-shrink: 0;
  }

  .task-title {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }

  .task-id {
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--text-muted);
  }

  .task-workflow {
    font-size: 12px;
    font-weight: 500;
    color: var(--text-primary);
    background: var(--bg-inset);
    border: 1px solid var(--border-muted);
    border-radius: var(--radius-sm);
    padding: 1px 6px;
  }

  .task-status {
    font-size: 11px;
    font-weight: 500;
    border-radius: var(--radius-sm);
    padding: 1px 6px;
  }

  .status-completed { background: color-mix(in srgb, var(--accent-green) 15%, transparent); color: var(--accent-green); }
  .status-failed, .status-error { background: color-mix(in srgb, var(--accent-red) 15%, transparent); color: var(--accent-red); }
  .status-running { background: color-mix(in srgb, var(--running-fg) 15%, transparent); color: var(--running-fg); }

  .task-error {
    margin-top: 6px;
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 11px;
    color: var(--accent-red);
    background: color-mix(in srgb, var(--accent-red) 10%, transparent);
    border-radius: var(--radius-sm);
    padding: 4px 8px;
  }

  .pipeline {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 0;
  }

  .stage {
    display: flex;
    gap: 12px;
    min-height: 52px;
  }

  .stage-connector {
    display: flex;
    flex-direction: column;
    align-items: center;
    flex-shrink: 0;
    width: 24px;
  }

  .stage-icon {
    width: 24px;
    height: 24px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    background: var(--bg-inset);
    color: var(--text-muted);
    border: 1px solid var(--border-default);
  }

  .stage-icon-ok {
    background: color-mix(in srgb, var(--accent-blue) 10%, transparent);
    color: var(--accent-blue);
    border-color: color-mix(in srgb, var(--accent-blue) 30%, transparent);
  }

  .stage-icon-err {
    background: color-mix(in srgb, var(--accent-red) 10%, transparent);
    color: var(--accent-red);
    border-color: color-mix(in srgb, var(--accent-red) 30%, transparent);
  }

  .stage-line {
    flex: 1;
    width: 1px;
    background: var(--border-default);
    margin: 3px 0;
    min-height: 16px;
  }

  .stage-body {
    flex: 1;
    padding-bottom: 16px;
    padding-top: 2px;
  }

  .stage-top {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 2px;
  }

  .stage-label {
    font-size: 12px;
    font-weight: 500;
    color: var(--text-primary);
  }

  .stage-badge {
    font-size: 10px;
    font-weight: 500;
    font-family: var(--font-mono);
    margin-left: auto;
  }

  :global(.stage-check) { color: var(--accent-green); margin-left: auto; }
  :global(.stage-err-icon) { color: var(--accent-red); margin-left: auto; }

  .stage-detail {
    font-size: 11px;
    color: var(--text-secondary);
  }

  .stage-meta {
    font-size: 10px;
    color: var(--text-muted);
    font-family: var(--font-mono);
    margin-top: 1px;
  }
</style>
