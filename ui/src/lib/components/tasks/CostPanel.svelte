<script>
  import { TrendingUpIcon, CoinsIcon, CpuIcon, TimerIcon } from '../../icons.js'
  import { fmtTokens, fmtDur } from '../../utils/format.js'
  import { tasksStore } from '../../stores/tasksStore.svelte'

  let summary = $derived(tasksStore.summary)
  let task = $derived(tasksStore.selected)

  let byAgent = $derived(
    summary?.by_agent
      ? Object.entries(summary.by_agent).sort((a, b) => b[1] - a[1])
      : []
  )

  let byModel = $derived(
    summary?.by_model
      ? Object.entries(summary.by_model).sort((a, b) => b[1] - a[1])
      : []
  )
</script>

<div class="cost-panel">
  {#if summary}
    <section class="panel-section">
      <div class="section-title">Обзор</div>
      <div class="cards">
        <div class="card">
          <CoinsIcon size="13" strokeWidth="2" />
          <span class="card-value">${(summary.total_cost_usd ?? 0).toFixed(4)}</span>
          <span class="card-label">расходы</span>
        </div>
        <div class="card">
          <CpuIcon size="13" strokeWidth="2" />
          <span class="card-value">{fmtTokens(summary.total_input_tokens + summary.total_output_tokens)}</span>
          <span class="card-label">токенов</span>
        </div>
        <div class="card">
          <TrendingUpIcon size="13" strokeWidth="2" />
          <span class="card-value">{fmtTokens(summary.total_saved_tokens)}</span>
          <span class="card-label">сэкономлено</span>
        </div>
        <div class="card">
          <TimerIcon size="13" strokeWidth="2" />
          <span class="card-value">{fmtDur(summary.avg_duration_ms)}</span>
          <span class="card-label">среднее время</span>
        </div>
      </div>
    </section>

    {#if byAgent.length}
      <section class="panel-section">
        <div class="section-title">По агентам</div>
        <div class="bar-list">
          {#each byAgent as [agent, count]}
            {@const pct = Math.round((count / summary.total_tasks) * 100)}
            <div class="bar-row">
              <span class="bar-label">{agent}</span>
              <div class="bar-track">
                <div class="bar-fill" style:width="{pct}%"></div>
              </div>
              <span class="bar-val">{count}</span>
            </div>
          {/each}
        </div>
      </section>
    {/if}

    {#if byModel.length}
      <section class="panel-section">
        <div class="section-title">По моделям</div>
        <div class="bar-list">
          {#each byModel.slice(0, 5) as [model, count]}
            {@const pct = Math.round((count / summary.total_tasks) * 100)}
            <div class="bar-row">
              <span class="bar-label">{model}</span>
              <div class="bar-track">
                <div class="bar-fill bar-fill-purple" style:width="{pct}%"></div>
              </div>
              <span class="bar-val">{count}</span>
            </div>
          {/each}
        </div>
      </section>
    {/if}

    <section class="panel-section">
      <div class="section-title">Статусы</div>
      <div class="status-grid">
        {#each Object.entries(summary.by_status ?? {}) as [s, n]}
          {@const r = { completed: 'выполнено', failed: 'ошибка', running: 'в работе', error: 'ошибка' }}
          <div class="status-chip status-{s}">
            <span class="status-n">{n}</span>
            <span class="status-name">{r[s] ?? s}</span>
          </div>
        {/each}
      </div>
    </section>
  {/if}

  {#if task}
    <section class="panel-section">
      <div class="section-title">Выбранная задача</div>
      <div class="task-detail-rows">
        <div class="detail-row"><span class="dr-label">Стоимость</span><span class="dr-val accent">${(task.cost_usd ?? 0).toFixed(6)}</span></div>
        <div class="detail-row"><span class="dr-label">Токены вход</span><span class="dr-val">{fmtTokens(task.tokens?.input)}</span></div>
        <div class="detail-row"><span class="dr-label">Токены выход</span><span class="dr-val">{fmtTokens(task.tokens?.output)}</span></div>
        <div class="detail-row"><span class="dr-label">RTK экономия</span><span class="dr-val saved">{fmtTokens(task.tokens?.saved_rtk)}</span></div>
        <div class="detail-row"><span class="dr-label">Headroom экон.</span><span class="dr-val saved">{fmtTokens(task.tokens?.saved_headroom)}</span></div>
        <div class="detail-row"><span class="dr-label">Кэш</span><span class="dr-val">{task.gateway?.cache_hit ? 'да' : 'нет'}</span></div>
        <div class="detail-row"><span class="dr-label">Длительность</span><span class="dr-val">{fmtDur(task.duration_ms)}</span></div>
        {#if task.automation_score != null}<div class="detail-row"><span class="dr-label">Автоматизация</span><span class="dr-val">{(task.automation_score * 100).toFixed(0)}%</span></div>{/if}
      </div>
    </section>
  {/if}
</div>

<style>
  .cost-panel {
    width: 240px;
    flex-shrink: 0;
    border-left: 1px solid var(--border-default);
    overflow-y: auto;
    background: var(--bg-surface);
  }

  .panel-section {
    padding: 10px 12px;
    border-bottom: 1px solid var(--border-muted);
  }

  .section-title {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-muted);
    margin-bottom: 8px;
  }

  .cards {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px;
  }

  .card {
    background: var(--bg-inset);
    border: 1px solid var(--border-muted);
    border-radius: var(--radius-sm);
    padding: 6px 8px;
    display: flex;
    flex-direction: column;
    gap: 2px;
    color: var(--text-muted);
  }

  .card-value {
    font-size: 13px;
    font-weight: 600;
    color: var(--text-primary);
    font-variant-numeric: tabular-nums;
  }

  .card-label {
    font-size: 10px;
    color: var(--text-muted);
  }

  .bar-list { display: flex; flex-direction: column; gap: 5px; }

  .bar-row {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .bar-label {
    font-size: 11px;
    color: var(--text-secondary);
    width: 72px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex-shrink: 0;
  }

  .bar-track {
    flex: 1;
    height: 4px;
    background: var(--bg-inset);
    border-radius: 2px;
    overflow: hidden;
  }

  .bar-fill {
    height: 100%;
    background: var(--accent-blue);
    border-radius: 2px;
    transition: width 0.3s;
  }

  .bar-fill-purple { background: var(--accent-purple); }

  .bar-val {
    font-size: 10px;
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
    width: 20px;
    text-align: right;
    flex-shrink: 0;
  }

  .status-grid {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }

  .status-chip {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 2px 6px;
    border-radius: var(--radius-sm);
    background: var(--bg-inset);
    border: 1px solid var(--border-muted);
  }

  .status-completed { color: var(--accent-green); }
  .status-failed, .status-error { color: var(--accent-red); }
  .status-running { color: var(--running-fg); }

  .status-n { font-size: 12px; font-weight: 600; }
  .status-name { font-size: 10px; color: var(--text-muted); }

  .task-detail-rows { display: flex; flex-direction: column; gap: 4px; }

  .detail-row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
  }

  .dr-label { font-size: 11px; color: var(--text-muted); }
  .dr-val {
    font-size: 11px;
    font-variant-numeric: tabular-nums;
    color: var(--text-secondary);
    font-family: var(--font-mono);
  }

  .dr-val.accent { color: var(--accent-amber); }
  .dr-val.saved { color: var(--accent-teal); }
</style>
