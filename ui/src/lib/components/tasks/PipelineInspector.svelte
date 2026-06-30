<script>
  import {
    RouteIcon, DatabaseIcon, ZapIcon, LayersIcon,
    BrainCircuitIcon, MessageSquareIcon, SaveIcon,
    BarChart2Icon, AlertCircleIcon, CheckCircle2Icon,
    ChevronRightIcon, BookOpenIcon, CoinsIcon, CpuIcon,
    ClockIcon, ActivityIcon,
  } from '../../icons.js'

  let { task = null } = $props()

  let promptCollapsed = $state(true)
  let outputCollapsed = $state(false)

  const stageLabels = {
    init: 'Инициализация',
    agui_start: 'AGUI старт',
    a2a_discover: 'A2A поиск',
    a2a_delegate: 'A2A делегат',
    route: 'Маршрутизация',
    memory_retrieve: 'Память',
    rtk_filter: 'RTK фильтр',
    skill_inject: 'Скилы',
    headroom_compress: 'Headroom',
    dspy_program_call: 'DSPy',
    model_call: 'Вызов модели',
    memory_store: 'Запись памяти',
    agui_done: 'AGUI финиш',
    done: 'Готово',
    error: 'Ошибка',
  }

  function pct(saved, total) {
    if (!total || !saved) return null
    return Math.round((saved / (total + saved)) * 100)
  }

  function fmtTokens(n) {
    if (!n) return '0'
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
    if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
    return String(n)
  }

  function fmtDur(ms) {
    if (!ms) return '—'
    if (ms < 1000) return `${Math.round(ms)}ms`
    return `${(ms / 1000).toFixed(1)}s`
  }

  function rel(mtime) {
    if (!mtime) return ''
    const d = new Date(mtime * 1000)
    const diff = (Date.now() - d) / 1000
    if (diff < 60) return 'только что'
    if (diff < 3600) return `${Math.round(diff / 60)}м назад`
    if (diff < 86400) return `${Math.round(diff / 3600)}ч назад`
    return d.toLocaleDateString('ru')
  }

  const statusRu = { completed: 'выполнено', failed: 'ошибка', running: 'в работе', error: 'ошибка' }

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
        id: 'route',
        label: 'Маршрутизация',
        hint: 'Выбирает лучшего агента и модель по ключевым словам, routing score, ограничениям по стоимости и возможностям агента.',
        icon: RouteIcon,
        detail: `${t.agent} → ${t.model}`,
        meta: t.provider ?? '',
        badge: t.routing_score ? `score ${(t.routing_score * 100).toFixed(0)}%` : null,
        ok: true,
      },
      {
        id: 'memory',
        label: 'Извлечение памяти',
        hint: 'Ищет релевантный контекст из прошлых задач в семантической памяти (Vectorize + D1). Совпавшие фрагменты инжектируются в промпт.',
        icon: DatabaseIcon,
        detail: t.skill_ids?.length ? `совпадений: ${t.skill_ids.length}` : 'нет совпадений',
        meta: t.skill_ids?.join(', ') ?? '',
        ok: true,
      },
      {
        id: 'rtk',
        label: 'RTK Фильтр',
        hint: 'Rust Token Killer — удаляет малоценные токены (debug-вывод, стек-трейсы, тестовый boilerplate) до отправки в модель. Снижает стоимость без потери контекста.',
        icon: ZapIcon,
        detail: savedRtk ? `сэкономлено ${savedRtk.toLocaleString()} токенов` : 'нет экономии',
        meta: savedRtk ? `${pct(savedRtk, totalIn)}% сокращение` : '',
        badge: savedRtk ? `-${savedRtk.toLocaleString()}` : null,
        badgeColor: savedRtk ? 'var(--accent-teal)' : null,
        ok: true,
      },
      {
        id: 'skill_inject',
        label: 'Инъекция скилов',
        hint: 'Сопоставляет установленные скилы из .codeops/skills/ с задачей и инжектирует их инструкции в системный промпт агента.',
        icon: BookOpenIcon,
        detail: t.skill_ids?.length
          ? `инжектировано: ${t.skill_ids.length}`
          : 'скилы не подошли',
        meta: t.skill_ids?.join(', ') ?? '',
        badge: t.skill_ids?.length ? `+${t.skill_ids.length}` : null,
        badgeColor: t.skill_ids?.length ? 'var(--accent-teal)' : null,
        ok: true,
      },
      {
        id: 'headroom',
        label: 'Сжатие контекста',
        hint: 'Сжимает контекст чтобы уместиться в лимит токенов модели. Использует семантическое разбиение для сохранения смысла.',
        icon: LayersIcon,
        detail: savedHr ? `сжато ${savedHr.toLocaleString()} токенов` : 'нет сжатия',
        meta: savedHr ? `${pct(savedHr, totalIn)}% сокращение` : '',
        badge: savedHr ? `-${savedHr.toLocaleString()}` : null,
        badgeColor: savedHr ? 'var(--accent-purple)' : null,
        ok: true,
      },
      ...(t.dspy_enabled ? [{
        id: 'dspy',
        label: 'DSPy Программа',
        hint: 'Оптимизированная prompt-программа, скомпилированная DSPy. В режиме shadow запускается параллельно для сбора обучающих данных.',
        icon: BrainCircuitIcon,
        detail: t.dspy_program_id ?? 'включён',
        meta: `режим: ${t.dspy_mode ?? 'shadow'} · тег: ${t.dspy_program_tag ?? '—'}`,
        badge: t.dspy_mode,
        ok: true,
      }] : []),
      {
        id: 'model_call',
        label: 'Вызов модели',
        hint: 'Реальный LLM API вызов через AI Gateway. Gateway добавляет DLP-сканирование, кэш ответов, лимиты расходов и автоматический fallback.',
        icon: MessageSquareIcon,
        detail: `${totalIn.toLocaleString()} вход · ${(tokens.output ?? 0).toLocaleString()} выход`,
        meta: [
          gw.cache_hit ? 'кэш попадание' : null,
          gw.fallback_used ? 'запасная модель' : null,
          gw.dlp_blocked ? 'DLP заблокировал' : null,
        ].filter(Boolean).join(' · ') || `${t.provider}`,
        badge: gw.cache_hit ? 'кэш' : null,
        badgeColor: gw.cache_hit ? 'var(--accent-green)' : null,
        ok: !gw.dlp_blocked,
      },
      {
        id: 'memory_store',
        label: 'Сохранение в память',
        hint: 'Сохраняет результат задачи и ключевые факты в семантическую память (Vectorize + D1).',
        icon: SaveIcon,
        detail: t.status === 'completed' ? 'сохранено в память' : 'пропущено',
        ok: t.status === 'completed',
      },
      {
        id: 'telemetry',
        label: 'Телеметрия',
        hint: 'Записывает стоимость, токены, длительность и данные стадий в CF Telemetry Worker.',
        icon: BarChart2Icon,
        detail: t.duration_ms ? `${(t.duration_ms / 1000).toFixed(2)}s итого` : '—',
        meta: `статус: ${statusRu[t.status] ?? t.status}`,
        ok: t.status === 'completed',
      },
    ]
  })

  // Empty state pipeline flow
  const emptyStages = [
    { icon: RouteIcon,        label: 'Маршрут' },
    { icon: DatabaseIcon,     label: 'Память' },
    { icon: ZapIcon,          label: 'RTK' },
    { icon: BookOpenIcon,     label: 'Скилы' },
    { icon: LayersIcon,       label: 'Headroom' },
    { icon: MessageSquareIcon,label: 'Модель' },
    { icon: SaveIcon,         label: 'Запись' },
    { icon: BarChart2Icon,    label: 'Телеметрия' },
  ]
</script>

{#if !task}
  <div class="empty-state">
    <div class="empty-icon">
      <ChevronRightIcon size="28" strokeWidth="1.5" />
    </div>
    <p class="empty-title">Выберите задачу для инспекции</p>
    <p class="empty-sub">Детали pipeline, токены, расходы и стадии выполнения</p>

    <div class="empty-flow">
      {#each emptyStages as s, i}
        {@const Icon = s.icon}
        <div class="ef-step">
          <div class="ef-icon"><Icon size="12" strokeWidth="2" /></div>
          <span class="ef-label">{s.label}</span>
        </div>
        {#if i < emptyStages.length - 1}
          <div class="ef-arrow">→</div>
        {/if}
      {/each}
    </div>
  </div>
{:else}
  <div class="inspector">

    <!-- Header -->
    <div class="inspector-header">
      <div class="header-top">
        <div class="task-title">
          <span class="task-id">{task.task_id?.slice(0, 8)}</span>
          {#if task.workflow}
            <span class="task-workflow">{task.workflow}</span>
          {/if}
          <span class="task-status status-{task.status}">{statusRu[task.status] ?? task.status}</span>
        </div>
        <span class="task-time">{rel(task._mtime)}</span>
      </div>

      <!-- Meta strip -->
      <div class="meta-strip">
        {#if task.agent}
          <span class="meta-item"><span class="meta-k">агент</span>{task.agent}</span>
        {/if}
        {#if task.model}
          <span class="meta-item"><span class="meta-k">модель</span>{task.model}</span>
        {/if}
        {#if task.provider}
          <span class="meta-item"><span class="meta-k">провайдер</span>{task.provider}</span>
        {/if}
        {#if task.executor}
          <span class="meta-item"><span class="meta-k">executor</span>{task.executor}</span>
        {/if}
        {#if task.task_type}
          <span class="meta-item"><span class="meta-k">тип</span>{task.task_type}</span>
        {/if}
      </div>

      {#if task.error}
        <div class="task-error">
          <AlertCircleIcon size="13" strokeWidth="2" />
          {task.error}
        </div>
      {/if}
    </div>

    <!-- Two-pane body -->
    <div class="inspector-body">

      <!-- LEFT: pipeline stages chronology -->
      <div class="left-pane">
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
              {#if stage.hint}
                <div class="stage-hint">{stage.hint}</div>
              {/if}
            </div>
          </div>
        {/each}
      </div>

      <!-- RIGHT: stats + details -->
      <div class="right-pane">

        <!-- Task prompt field -->
        {#if task.task_prompt}
          <div class="task-prompt-field">
            <span class="task-prompt-label">Задача</span>
            <div class="task-prompt-text">{task.task_prompt}</div>
          </div>
        {/if}

        <!-- Stats cards -->
        <div class="stats-strip">
          <div class="stat-card">
            <CoinsIcon size="12" strokeWidth="2" />
            <span class="stat-val">${(task.cost_usd ?? 0).toFixed(5)}</span>
            <span class="stat-lbl">стоимость</span>
          </div>
          <div class="stat-card">
            <CpuIcon size="12" strokeWidth="2" />
            <span class="stat-val">{fmtTokens((task.tokens?.input ?? 0) + (task.tokens?.output ?? 0))}</span>
            <span class="stat-lbl">токенов</span>
          </div>
          {#if (task.tokens?.saved_rtk ?? 0) + (task.tokens?.saved_headroom ?? 0) > 0}
            <div class="stat-card saved">
              <ZapIcon size="12" strokeWidth="2" />
              <span class="stat-val">{fmtTokens((task.tokens?.saved_rtk ?? 0) + (task.tokens?.saved_headroom ?? 0))}</span>
              <span class="stat-lbl">сэкономлено</span>
            </div>
          {/if}
          <div class="stat-card">
            <ClockIcon size="12" strokeWidth="2" />
            <span class="stat-val">{fmtDur(task.duration_ms)}</span>
            <span class="stat-lbl">время</span>
          </div>
          {#if task.routing_score}
            <div class="stat-card">
              <ActivityIcon size="12" strokeWidth="2" />
              <span class="stat-val">{(task.routing_score * 100).toFixed(0)}%</span>
              <span class="stat-lbl">routing</span>
            </div>
          {/if}
        </div>

        <!-- Token flow bar -->
        {#if tokenBar.length > 0}
          <div class="token-bar-wrap">
            <div class="token-bar">
              {#each tokenBar as seg}
                <div
                  class="token-seg"
                  style:width="{seg.pct}%"
                  style:background={seg.color}
                  title="{seg.label}: {seg.value.toLocaleString()} токенов ({seg.pct}%)"
                ></div>
              {/each}
            </div>
            <div class="token-legend">
              {#each tokenBar as seg}
                <span class="token-leg-item">
                  <span class="leg-dot" style:background={seg.color}></span>
                  {seg.label} {fmtTokens(seg.value)}
                </span>
              {/each}
            </div>
          </div>
        {/if}

        <div class="right-sections">

          <!-- Work report -->
          {#if task.report}
            {@const rpt = task.report}
            <div class="report-block">
              {#if rpt.summary}
                <div class="report-summary">{rpt.summary}</div>
              {/if}

              {#if rpt.files_created?.length || rpt.files_changed?.length || rpt.files_deleted?.length}
                <div class="report-files">
                  {#each rpt.files_created ?? [] as f}
                    <div class="rf-row rf-created"><span class="rf-icon">+</span><span class="rf-path">{f}</span></div>
                  {/each}
                  {#each rpt.files_changed ?? [] as f}
                    <div class="rf-row rf-changed"><span class="rf-icon">~</span><span class="rf-path">{f}</span></div>
                  {/each}
                  {#each rpt.files_deleted ?? [] as f}
                    <div class="rf-row rf-deleted"><span class="rf-icon">−</span><span class="rf-path">{f}</span></div>
                  {/each}
                </div>
              {/if}

              {#if rpt.actions?.length}
                <ul class="report-actions">
                  {#each rpt.actions as action}
                    <li>{action}</li>
                  {/each}
                </ul>
              {/if}
            </div>
          {/if}

          <!-- LLM output -->
          {#if task.result}
            <div class="extras-section">
              <button class="section-toggle" onclick={() => outputCollapsed = !outputCollapsed}>
                <span class="extras-title" style="margin: 0">Вывод</span>
                <span class="toggle-chip">{(task.tokens?.output ?? 0).toLocaleString()} tok</span>
                <span class="toggle-arrow" class:rotated={!outputCollapsed}>›</span>
              </button>
              {#if !outputCollapsed}
                <div class="text-block output-block">{task.result}</div>
              {/if}
            </div>
          {/if}

          <!-- Stage history / timing -->
          {#if task.stage_log?.length}
            <div class="extras-section">
              <div class="extras-title">История выполнения</div>
              <div class="stage-timeline">
                {#each task.stage_log as entry, i}
                  <div class="tl-row">
                    <span class="tl-dot" class:tl-last={i === task.stage_log.length - 1}></span>
                    <span class="tl-label">{stageLabels[entry.stage] ?? entry.stage}</span>
                    <span class="tl-time">+{entry.elapsed_ms}ms</span>
                    {#if i > 0}
                      {@const delta = entry.elapsed_ms - task.stage_log[i - 1].elapsed_ms}
                      {#if delta > 5}
                        <span class="tl-delta">(+{delta}ms)</span>
                      {/if}
                    {/if}
                  </div>
                {/each}
              </div>
            </div>
          {/if}

          <!-- Gateway details -->
          {#if task.gateway}
            {@const gw = task.gateway}
            <div class="extras-section">
              <div class="extras-title">Gateway</div>
              <div class="extras-grid">
                <div class="extra-row">
                  <span class="extra-k">Кэш</span>
                  <span class="extra-v" class:ok={gw.cache_hit} class:muted={!gw.cache_hit}>
                    {gw.cache_hit ? 'попадание ✓' : 'промах'}
                  </span>
                </div>
                <div class="extra-row">
                  <span class="extra-k">Fallback</span>
                  <span class="extra-v" class:warn={gw.fallback_used} class:muted={!gw.fallback_used}>
                    {gw.fallback_used ? 'использован' : 'не нужен'}
                  </span>
                </div>
                <div class="extra-row">
                  <span class="extra-k">DLP</span>
                  <span class="extra-v" class:err={gw.dlp_blocked} class:muted={!gw.dlp_blocked}>
                    {gw.dlp_blocked ? 'заблокировал' : 'пропущено'}
                  </span>
                </div>
                {#if task.provider}
                  <div class="extra-row">
                    <span class="extra-k">Провайдер</span>
                    <span class="extra-v">{task.provider}</span>
                  </div>
                {/if}
              </div>
            </div>
          {/if}

          <!-- DSPy details -->
          {#if task.dspy_enabled}
            <div class="extras-section">
              <div class="extras-title">DSPy</div>
              <div class="extras-grid">
                <div class="extra-row">
                  <span class="extra-k">Режим</span>
                  <span class="extra-v">{task.dspy_mode ?? '—'}</span>
                </div>
                {#if task.dspy_program_id}
                  <div class="extra-row">
                    <span class="extra-k">Программа</span>
                    <span class="extra-v mono">{task.dspy_program_id}</span>
                  </div>
                {/if}
                {#if task.dspy_program_version}
                  <div class="extra-row">
                    <span class="extra-k">Версия</span>
                    <span class="extra-v">v{task.dspy_program_version}</span>
                  </div>
                {/if}
                {#if task.dspy_program_tag}
                  <div class="extra-row">
                    <span class="extra-k">Тег</span>
                    <span class="extra-v">{task.dspy_program_tag}</span>
                  </div>
                {/if}
                {#if task.dspy_score != null}
                  <div class="extra-row">
                    <span class="extra-k">Score</span>
                    <span class="extra-v ok">{(task.dspy_score * 100).toFixed(1)}%</span>
                  </div>
                {/if}
                {#if task.dspy_shadow_delta != null}
                  <div class="extra-row">
                    <span class="extra-k">Shadow delta</span>
                    <span class="extra-v">{task.dspy_shadow_delta > 0 ? '+' : ''}{task.dspy_shadow_delta.toFixed(3)}</span>
                  </div>
                {/if}
              </div>
            </div>
          {/if}

          <!-- Task metadata -->
          <div class="extras-section">
            <div class="extras-title">Метаданные</div>
            <div class="extras-grid">
              <div class="extra-row">
                <span class="extra-k">Task ID</span>
                <span class="extra-v mono">{task.task_id}</span>
              </div>
              {#if task.task_type}
                <div class="extra-row">
                  <span class="extra-k">Тип</span>
                  <span class="extra-v">{task.task_type}</span>
                </div>
              {/if}
              {#if task.routing_score}
                <div class="extra-row">
                  <span class="extra-k">Routing</span>
                  <span class="extra-v">{(task.routing_score * 100).toFixed(1)}%</span>
                </div>
              {/if}
              {#if task.automation_score}
                <div class="extra-row">
                  <span class="extra-k">Автоматизация</span>
                  <span class="extra-v">{(task.automation_score * 100).toFixed(0)}%</span>
                </div>
              {/if}
              {#if task.manual_steps_removed}
                <div class="extra-row">
                  <span class="extra-k">Шагов убрано</span>
                  <span class="extra-v ok">{task.manual_steps_removed}</span>
                </div>
              {/if}
              {#if task.skill_ids?.length}
                <div class="extra-row">
                  <span class="extra-k">Скилы</span>
                  <span class="extra-v mono">{task.skill_ids.join(', ')}</span>
                </div>
              {/if}
            </div>
          </div>

        </div><!-- /right-sections -->
      </div><!-- /right-pane -->
    </div><!-- /inspector-body -->
  </div>
{/if}

<style>
  /* ── Empty state ── */
  .empty-state {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 8px;
    color: var(--text-muted);
    padding: 32px;
  }

  .empty-icon { color: var(--border-default); }

  .empty-title {
    font-size: 13px;
    font-weight: 500;
    color: var(--text-secondary);
    margin: 0;
  }

  .empty-sub {
    font-size: 11px;
    color: var(--text-muted);
    margin: 0 0 16px;
  }

  .empty-flow {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 4px;
    justify-content: center;
    max-width: 480px;
  }

  .ef-step {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 3px;
  }

  .ef-icon {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background: var(--bg-inset);
    border: 1px solid var(--border-muted);
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-muted);
  }

  .ef-label {
    font-size: 9px;
    color: var(--text-muted);
    white-space: nowrap;
  }

  .ef-arrow {
    font-size: 11px;
    color: var(--border-default);
    margin-bottom: 12px;
  }

  /* ── Inspector ── */
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

  /* LEFT pane — pipeline stages */
  .left-pane {
    flex: 1;
    min-width: 0;
    border-right: 1px solid var(--border-default);
    overflow-y: auto;
    padding: 14px 14px 14px 16px;
    display: flex;
    flex-direction: column;
  }

  /* RIGHT pane — stats + details */
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

  /* Header */
  .inspector-header {
    padding: 10px 16px;
    border-bottom: 1px solid var(--border-default);
    flex-shrink: 0;
  }

  .header-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 5px;
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

  .task-time {
    font-size: 10px;
    color: var(--text-muted);
    flex-shrink: 0;
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

  /* Meta strip */
  .meta-strip {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    font-size: 11px;
  }

  .meta-item {
    display: flex;
    align-items: center;
    gap: 4px;
    color: var(--text-secondary);
  }

  .meta-k {
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-muted);
    font-weight: 600;
  }

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

  /* Task prompt field */
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

  /* Stats strip */
  .stats-strip {
    display: flex;
    gap: 1px;
    border-bottom: 1px solid var(--border-default);
    flex-shrink: 0;
    background: var(--border-muted);
  }

  .stat-card {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1px;
    padding: 6px 4px;
    background: var(--bg-surface);
    color: var(--text-muted);
  }

  .stat-card.saved { color: var(--accent-teal); }

  .stat-val {
    font-size: 13px;
    font-weight: 600;
    color: var(--text-primary);
    font-variant-numeric: tabular-nums;
    line-height: 1;
  }

  .stat-card.saved .stat-val { color: var(--accent-teal); }

  .stat-lbl {
    font-size: 9px;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  /* Token bar */
  .token-bar-wrap {
    padding: 8px 16px 6px;
    border-bottom: 1px solid var(--border-muted);
    flex-shrink: 0;
  }

  .token-bar {
    height: 6px;
    border-radius: 3px;
    overflow: hidden;
    display: flex;
    gap: 1px;
    margin-bottom: 5px;
    background: var(--bg-inset);
  }

  .token-seg {
    height: 100%;
    border-radius: 2px;
    transition: width 0.3s;
    min-width: 2px;
  }

  .token-legend {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .token-leg-item {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 10px;
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
  }

  .leg-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  /* Pipeline stages */
  .stage {
    display: flex;
    gap: 12px;
    min-height: 48px;
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
    min-height: 12px;
  }

  .stage-body {
    flex: 1;
    padding-bottom: 14px;
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

  .stage-detail { font-size: 11px; color: var(--text-secondary); }

  .stage-meta {
    font-size: 10px;
    color: var(--text-muted);
    font-family: var(--font-mono);
    margin-top: 1px;
  }

  .stage-hint {
    font-size: 10px;
    color: var(--text-muted);
    line-height: 1.4;
    margin-top: 3px;
    font-style: italic;
  }

  /* Extras sections */
  .extras-section {
    margin-top: 16px;
    padding-top: 12px;
    border-top: 1px solid var(--border-muted);
  }

  .extras-title {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-muted);
    margin-bottom: 7px;
  }

  .extras-grid { display: flex; flex-direction: column; gap: 3px; }

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

  /* ── Work report ── */
  .report-block {
    padding: 10px 14px 10px;
    border-bottom: 1px solid var(--border-default);
    display: flex;
    flex-direction: column;
    gap: 8px;
    flex-shrink: 0;
  }

  .report-summary {
    font-size: 11.5px;
    color: var(--text-primary);
    line-height: 1.55;
    white-space: pre-wrap;
    word-break: break-word;
  }

  .report-files {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .rf-row {
    display: flex;
    align-items: baseline;
    gap: 6px;
    font-size: 10.5px;
    font-family: var(--font-mono);
  }

  .rf-icon {
    width: 10px;
    flex-shrink: 0;
    font-weight: 700;
    text-align: center;
  }

  .rf-path {
    color: var(--text-secondary);
    word-break: break-all;
  }

  .rf-created .rf-icon { color: var(--accent-green); }
  .rf-changed .rf-icon { color: var(--accent-amber); }
  .rf-deleted .rf-icon { color: var(--accent-red); }

  .report-actions {
    margin: 0;
    padding: 0 0 0 14px;
    display: flex;
    flex-direction: column;
    gap: 3px;
  }

  .report-actions li {
    font-size: 11px;
    color: var(--text-secondary);
    line-height: 1.4;
  }

  /* ── Collapsible sections ── */
  .section-toggle {
    display: flex;
    align-items: center;
    gap: 6px;
    width: 100%;
    text-align: left;
    background: transparent;
    padding: 0;
    margin-bottom: 0;
    cursor: pointer;
  }

  .section-toggle:hover .extras-title { color: var(--text-primary); }

  .toggle-arrow {
    font-size: 14px;
    color: var(--text-muted);
    margin-left: auto;
    transition: transform 0.15s;
    line-height: 1;
  }
  .toggle-arrow.rotated { transform: rotate(90deg); }

  .toggle-chip {
    font-size: 10px;
    color: var(--text-muted);
    background: var(--bg-inset);
    border-radius: 3px;
    padding: 1px 5px;
    font-variant-numeric: tabular-nums;
  }

  /* ── Text blocks ── */
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

  /* ── Stage timeline ── */
  .stage-timeline {
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin-top: 6px;
  }

  .tl-row {
    display: flex;
    align-items: center;
    gap: 7px;
    font-size: 11px;
  }

  .tl-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--accent-blue);
    flex-shrink: 0;
  }

  .tl-last { background: var(--accent-green); }

  .tl-label {
    color: var(--text-secondary);
    min-width: 110px;
  }

  .tl-time {
    font-family: var(--font-mono);
    font-size: 10px;
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
  }

  .tl-delta {
    font-size: 10px;
    color: var(--accent-amber);
    font-variant-numeric: tabular-nums;
  }
</style>
