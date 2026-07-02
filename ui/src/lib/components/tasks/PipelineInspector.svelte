<script>
  import {
    RouteIcon, DatabaseIcon, ZapIcon, LayersIcon,
    BrainCircuitIcon, MessageSquareIcon, SaveIcon,
    BarChart2Icon, BookOpenIcon,
  } from '../../icons.js'
  import { statusRu, calcPct } from '../../utils/format.js'
  import { tasksStore } from '../../stores/tasksStore.svelte'
  import PipelineEmptyState from './PipelineEmptyState.svelte'
  import TaskHeader from './TaskHeader.svelte'
  import PipelineStages from './PipelineStages.svelte'
  import StatsOverview from './StatsOverview.svelte'
  import WorkReport from './WorkReport.svelte'
  import ExtrasSection from './ExtrasSection.svelte'

  let outputExpanded = $state(true)
  let task = $derived(tasksStore.selected)

  // Token flow bar segments
  let tokenBar = $derived.by(() => {
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
      { label: 'Вход',    value: input,    pct: seg(input),    color: 'var(--accent-blue)' },
      { label: 'Выход',   value: output,   pct: seg(output),   color: 'var(--accent-indigo)' },
    ].filter(s => s.value > 0)
  })

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
        id: 'route', label: 'Маршрутизация',
        hint: 'Выбирает лучшего агента и модель по ключевым словам, routing score, ограничениям по стоимости и возможностям агента.',
        icon: RouteIcon, detail: `${t.agent} → ${t.model}`, meta: t.provider ?? '',
        badge: t.routing_score ? `score ${(t.routing_score * 100).toFixed(0)}%` : null, ok: true,
      },
      {
        id: 'memory', label: 'Извлечение памяти',
        hint: 'Ищет релевантный контекст из прошлых задач в семантической памяти (Vectorize + D1). Совпавшие фрагменты инжектируются в промпт.',
        icon: DatabaseIcon, detail: t.memory_hits ? `совпадений: ${t.memory_hits}` : 'нет совпадений',
        meta: '', badge: t.memory_hits ? `+${t.memory_hits}` : null,
        badgeColor: t.memory_hits ? 'var(--accent-blue)' : null, ok: true,
      },
      {
        id: 'rtk', label: 'RTK Фильтр',
        hint: 'Rust Token Killer — удаляет малоценные токены (debug-вывод, стек-трейсы, тестовый boilerplate) до отправки в модель. Снижает стоимость без потери контекста.',
        icon: ZapIcon,
        detail: savedRtk ? `сэкономлено ${savedRtk.toLocaleString()} токенов` : 'нет экономии',
        meta: savedRtk ? `${calcPct(savedRtk, totalIn)}% сокращение` : '',
        badge: savedRtk ? `-${savedRtk.toLocaleString()}` : null,
        badgeColor: savedRtk ? 'var(--accent-teal)' : null, ok: true,
      },
      {
        id: 'skill_inject', label: 'Инъекция скилов',
        hint: 'Сопоставляет установленные скилы из .codeops/skills/ с задачей и инжектирует их инструкции в системный промпт агента.',
        icon: BookOpenIcon,
        detail: t.skill_ids?.length ? `инжектировано: ${t.skill_ids.length}` : 'скилы не подошли',
        meta: t.skill_ids?.join(', ') ?? '',
        badge: t.skill_ids?.length ? `+${t.skill_ids.length}` : null,
        badgeColor: t.skill_ids?.length ? 'var(--accent-teal)' : null, ok: true,
      },
      {
        id: 'headroom', label: 'Сжатие контекста',
        hint: 'Сжимает контекст чтобы уместиться в лимит токенов модели. Использует семантическое разбиение для сохранения смысла.',
        icon: LayersIcon,
        detail: savedHr ? `сжато ${savedHr.toLocaleString()} токенов` : 'нет сжатия',
        meta: savedHr ? `${calcPct(savedHr, totalIn)}% сокращение` : '',
        badge: savedHr ? `-${savedHr.toLocaleString()}` : null,
        badgeColor: savedHr ? 'var(--accent-purple)' : null, ok: true,
      },
      ...(t.dspy_enabled ? [{
        id: 'dspy', label: 'DSPy Программа',
        hint: 'Оптимизированная prompt-программа, скомпилированная DSPy. В режиме shadow запускается параллельно для сбора обучающих данных.',
        icon: BrainCircuitIcon, detail: t.dspy_program_id ?? 'включён',
        meta: `режим: ${t.dspy_mode ?? 'shadow'} · тег: ${t.dspy_program_tag ?? '—'}`,
        badge: t.dspy_mode, ok: true,
      }] : []),
      {
        id: 'model_call', label: 'Вызов модели',
        hint: 'Реальный LLM API вызов через AI Gateway. Gateway добавляет DLP-сканирование, кэш ответов, лимиты расходов и автоматический fallback.',
        icon: MessageSquareIcon,
        detail: `${totalIn.toLocaleString()} вход · ${(tokens.output ?? 0).toLocaleString()} выход`,
        meta: [
          gw.cache_hit ? 'кэш попадание' : null,
          gw.fallback_used ? `fallback → ${gw.fallback_model || '?'}` : null,
          gw.dlp_blocked ? 'DLP заблокировал' : null,
        ].filter(Boolean).join(' · ') || `${t.provider ?? ''}`,
        badge: gw.cache_hit ? 'кэш' : (gw.fallback_used ? 'fallback' : null),
        badgeColor: gw.cache_hit ? 'var(--accent-green)' : (gw.fallback_used ? 'var(--accent-amber)' : null),
        ok: !gw.dlp_blocked,
      },
      {
        id: 'memory_store', label: 'Сохранение в память',
        hint: 'Сохраняет результат задачи и ключевые факты в семантическую память (Vectorize + D1).',
        icon: SaveIcon, detail: t.status === 'completed' ? 'сохранено в память' : 'пропущено', ok: t.status === 'completed',
      },
      {
        id: 'telemetry', label: 'Телеметрия',
        hint: 'Записывает стоимость, токены, длительность и данные стадий в CF Telemetry Worker.',
        icon: BarChart2Icon,
        detail: t.duration_ms ? `${(t.duration_ms / 1000).toFixed(2)}s итого` : '—',
        meta: `статус: ${statusRu[t.status] ?? t.status}`, ok: t.status === 'completed',
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
            <span class="task-prompt-label">Задача</span>
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

        <div class="right-sections">
          {#if task.result}
            <ExtrasSection title="Вывод" chip="{(task.tokens?.output ?? 0).toLocaleString()} tok" collapsible bind:expanded={outputExpanded}>
              <div class="text-block output-block">{task.result}</div>
            </ExtrasSection>
          {/if}

          {#if task.a2a_dispatched && task.a2a_assignments?.length}
            <ExtrasSection title="Мульти-агенты" chip="{task.a2a_assignments.length} ролей">
              <div class="agents-list">
                {#each task.a2a_assignments as a}
                  <div class="agent-row">
                    <div class="agent-dot" style="background:{a.ok ? 'var(--accent-green)' : 'var(--accent-red)'}"></div>
                    <span class="agent-role">{a.role}</span>
                    <span class="agent-tier tier-{a.tier}">{a.tier}</span>
                    <span class="agent-model">{a.provider}/{a.model?.split('/').pop()}</span>
                    {#if a.cache_hit}<span class="agent-badge cached">cached</span>{/if}
                    {#if a.mem_hits}<span class="agent-badge mem">mem {a.mem_hits}</span>{/if}
                    <div class="agent-skills">
                      {#each a.skills ?? [] as s}<span class="agent-skill">{s}</span>{/each}
                    </div>
                    <span class="agent-cost">${(a.cost_usd ?? 0).toFixed(4)}</span>
                  </div>
                {/each}
              </div>
            </ExtrasSection>
          {/if}

          {#if task.gateway}
            {@const gw = task.gateway}
            <ExtrasSection title="Gateway">
              <div class="extras-grid">
                <div class="extra-row"><span class="extra-k">Кэш</span><span class="extra-v" class:ok={gw.cache_hit} class:muted={!gw.cache_hit}>{gw.cache_hit ? 'попадание ✓' : 'промах'}</span></div>
                <div class="extra-row">
                  <span class="extra-k">Fallback</span>
                  <span class="extra-v" class:warn={gw.fallback_used} class:muted={!gw.fallback_used}>
                    {#if gw.fallback_used}
                      использован → {gw.fallback_model || '?'}{gw.fallback_provider ? ` (${gw.fallback_provider})` : ''}
                    {:else}
                      не нужен
                    {/if}
                  </span>
                </div>
                {#if gw.fallback_used && gw.fallback_reason}
                  <div class="extra-row fallback-reason-row">
                    <span class="extra-k">Причина</span>
                    <span class="extra-v err fallback-reason" title={gw.fallback_reason}>{gw.fallback_reason}</span>
                  </div>
                {/if}
                <div class="extra-row"><span class="extra-k">DLP</span><span class="extra-v" class:err={gw.dlp_blocked} class:muted={!gw.dlp_blocked}>{gw.dlp_blocked ? 'заблокировал' : 'пропущено'}</span></div>
                {#if task.provider}
                  <div class="extra-row"><span class="extra-k">Провайдер</span><span class="extra-v">{task.provider}</span></div>
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
                <div class="extra-row"><span class="extra-k">Режим</span><span class="extra-v">{task.dspy_mode ?? '—'}</span></div>
                {#if task.dspy_program_id}<div class="extra-row"><span class="extra-k">Программа</span><span class="extra-v mono">{task.dspy_program_id}</span></div>{/if}
                {#if task.dspy_program_version}<div class="extra-row"><span class="extra-k">Версия</span><span class="extra-v">v{task.dspy_program_version}</span></div>{/if}
                {#if task.dspy_program_tag}<div class="extra-row"><span class="extra-k">Тег</span><span class="extra-v">{task.dspy_program_tag}</span></div>{/if}
                {#if task.dspy_score != null}<div class="extra-row"><span class="extra-k">Score</span><span class="extra-v ok">{(task.dspy_score * 100).toFixed(1)}%</span></div>{/if}
                {#if task.dspy_shadow_delta != null}<div class="extra-row"><span class="extra-k">Shadow delta</span><span class="extra-v">{task.dspy_shadow_delta > 0 ? '+' : ''}{task.dspy_shadow_delta.toFixed(3)}</span></div>{/if}
              </div>
            </ExtrasSection>
          {/if}

          <ExtrasSection title="Метаданные">
            <div class="extras-grid">
              <div class="extra-row"><span class="extra-k">Task ID</span><span class="extra-v mono">{task.task_id}</span></div>
              {#if task.task_type}<div class="extra-row"><span class="extra-k">Тип</span><span class="extra-v">{task.task_type}</span></div>{/if}
              {#if task.routing_score}<div class="extra-row"><span class="extra-k">Routing</span><span class="extra-v">{(task.routing_score * 100).toFixed(1)}%</span></div>{/if}
              {#if task.automation_score}<div class="extra-row"><span class="extra-k">Автоматизация</span><span class="extra-v">{(task.automation_score * 100).toFixed(0)}%</span></div>{/if}
              {#if task.manual_steps_removed}<div class="extra-row"><span class="extra-k">Шагов убрано</span><span class="extra-v ok">{task.manual_steps_removed}</span></div>{/if}
              {#if task.skill_ids?.length}<div class="extra-row"><span class="extra-k">Скилы</span><span class="extra-v mono">{task.skill_ids.join(', ')}</span></div>{/if}
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
  .agent-skills { display: flex; gap: 3px; flex-wrap: wrap; flex: 1; }
  .agent-skill {
    font-size: 9px; font-family: var(--font-mono); border-radius: var(--radius-sm); padding: 0 5px;
    background: color-mix(in srgb, var(--accent-teal) 12%, transparent);
    border: 1px solid color-mix(in srgb, var(--accent-teal) 30%, transparent); color: var(--accent-teal);
  }
  .agent-cost { font-size: 10px; color: var(--text-muted); font-variant-numeric: tabular-nums; min-width: 52px; text-align: right; }

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
