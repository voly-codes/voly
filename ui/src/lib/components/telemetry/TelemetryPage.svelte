<script lang="ts">
  // Telemetry dashboard: total cost/tokens/tasks (30d), daily spend & token
  // bar charts, top agents/models by spend. Data via GET /api/telemetry/summary.
  import { onMount } from 'svelte'
  import {
    CoinsIcon, CpuIcon, BarChart2Icon, TrendingUpIcon,
    ClockIcon, ArrowDownWideNarrowIcon, RefreshCwIcon,
    AlertCircleIcon, CheckCircle2Icon,
  } from '../../icons.js'
  import { fetchTelemetry } from '../../api/client.js'
  import { fmtTokens } from '../../utils/format.js'
  import Spinner from '../shared/Spinner.svelte'
  import { t } from '../../i18n/localeStore.svelte.ts'

  let data = $state<any>(null)
  let loading = $state(true)
  let error = $state<string | null>(null)

  async function load() {
    loading = true
    error = null
    try {
      data = await fetchTelemetry(30)
    } catch (e: any) {
      error = e.message
    } finally {
      loading = false
    }
  }

  onMount(load)

  function maxCost(arr: any[]) {
    return Math.max(...arr.map((d: any) => d.cost), 0.01)
  }

  function dailyMax() {
    return maxCost(data?.daily ?? [])
  }

  function agentMax() {
    return maxCost(data?.by_agent ?? [])
  }

  function modelMax() {
    return maxCost(data?.by_model ?? [])
  }

  function tokenMax() {
    const arr = data?.daily ?? []
    if (!arr.length) return 1
    return Math.max(...arr.map((d: any) => d.tokens), 1)
  }
</script>

<div class="telemetry-page">
  {#if loading}
    <div class="center-loading"><Spinner size={24} /> {t('tel.loading')}</div>

  {:else if error}
    <div class="error-block">
      <AlertCircleIcon size="16" strokeWidth="2" />
      <span>{error}</span>
      <button onclick={load}>{t('common.retry')}</button>
    </div>

  {:else if data}
    <!-- Summary cards -->
    <div class="summary-row">
      <div class="summary-card">
        <CoinsIcon size="14" strokeWidth="2" />
        <span class="sc-val">${data.total_cost.toFixed(4)}</span>
        <span class="sc-lbl">{t('tel.totalCost')}</span>
      </div>
      <div class="summary-card">
        <CpuIcon size="14" strokeWidth="2" />
        <span class="sc-val">{fmtTokens(data.total_tokens)}</span>
        <span class="sc-lbl">{t('tel.totalTokens')}</span>
      </div>
      <div class="summary-card">
        <BarChart2Icon size="14" strokeWidth="2" />
        <span class="sc-val">{data.total_tasks}</span>
        <span class="sc-lbl">{t('tel.totalTasks')}</span>
      </div>
      <div class="summary-card">
        <TrendingUpIcon size="14" strokeWidth="2" />
        <span class="sc-val">{data.daily.length}</span>
        <span class="sc-lbl">{t('tel.activeDays')}</span>
      </div>
    </div>

    <div class="section-hint">{t('tel.dataHint1')} <code>.voly/events/</code> {t('tel.dataHint2')}</div>

    <!-- Daily spend chart -->
    <section class="chart-section">
      <div class="chart-title">{t('tel.dailySpend')}</div>
      <div class="chart-hint">{t('tel.dailySpendHint')}</div>
      <div class="bar-chart">
        {#each data.daily as day}
          {@const pct = dailyMax() ? (day.cost / dailyMax()) * 100 : 0}
          <div class="bar-col" title="{day.date}: ${day.cost.toFixed(4)} — {day.tasks} tasks">
            <div class="bar" style:height="{Math.max(pct, 1)}%"></div>
            <span class="bar-date">{day.date.slice(5)}</span>
          </div>
        {/each}
      </div>
      <div class="chart-legend">
        <span class="legend-item"><span class="legend-dot"></span>Cost in USD</span>
        <span class="legend-item"><span class="legend-dot dark"></span>Tokens</span>
      </div>
    </section>

    <!-- Tokens chart -->
    <section class="chart-section">
      <div class="chart-title">{t('tel.dailyTokens')}</div>
      <div class="chart-hint">{t('tel.dailyTokensHint')}</div>
      <div class="bar-chart">
        {#each data.daily as day}
          {@const pct = (day.tokens / tokenMax()) * 100}
          <div class="bar-col" title="{day.date}: {fmtTokens(day.tokens)}">
            <div class="bar dark" style:height="{Math.max(pct, 1)}%"></div>
            <span class="bar-date">{day.date.slice(5)}</span>
          </div>
        {/each}
      </div>
    </section>

    <div class="two-col">
      <!-- Top by agent -->
      {#if data.by_agent?.length}
        <section class="chart-section">
          <div class="chart-title">{t('tel.topAgents')}</div>
          <div class="chart-hint">{t('tel.topAgentsHint')}</div>
          <div class="bar-list">
            {#each data.by_agent as a}
              {@const pct = agentMax() ? (a.cost / agentMax()) * 100 : 0}
              <div class="bar-row">
                <span class="bar-label">{a.name}</span>
                <div class="bar-track">
                  <div class="bar-fill blue" style:width="{pct}%"></div>
                </div>
                <span class="bar-val">${a.cost.toFixed(3)}</span>
              </div>
            {/each}
          </div>
        </section>
      {/if}

      <!-- Top by model -->
      {#if data.by_model?.length}
        <section class="chart-section">
          <div class="chart-title">{t('tel.topModels')}</div>
          <div class="chart-hint">{t('tel.topModelsHint')}</div>
          <div class="bar-list">
            {#each data.by_model.slice(0, 8) as m}
              {@const pct = modelMax() ? (m.cost / modelMax()) * 100 : 0}
              <div class="bar-row">
                <span class="bar-label">{m.name}</span>
                <div class="bar-track">
                  <div class="bar-fill purple" style:width="{pct}%"></div>
                </div>
                <span class="bar-val">${m.cost.toFixed(3)}</span>
              </div>
            {/each}
          </div>
        </section>
      {/if}
    </div>

    <div class="refresh-row">
      <button class="refresh-btn" onclick={load}>
        <RefreshCwIcon size="13" strokeWidth="2" />
        Refresh
      </button>
    </div>
  {/if}
</div>

<style>
  .telemetry-page {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 14px;
  }

  .center-loading {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 10px;
    font-size: 13px;
    color: var(--text-muted);
  }

  .error-block {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    color: var(--accent-red);
    background: color-mix(in srgb, var(--accent-red) 10%, transparent);
    border: 1px solid color-mix(in srgb, var(--accent-red) 25%, transparent);
    border-radius: var(--radius-md);
    padding: 12px 16px;
  }

  .error-block button {
    margin-left: auto;
    padding: 4px 12px;
    border: 1px solid currentColor;
    border-radius: var(--radius-sm);
    font-size: 11px;
  }

  .summary-row {
    display: flex;
    gap: 8px;
  }

  .summary-card {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 3px;
    padding: 12px 8px;
    background: var(--bg-surface);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    color: var(--text-muted);
  }

  .sc-val {
    font-size: 15px;
    font-weight: 600;
    color: var(--text-primary);
    font-variant-numeric: tabular-nums;
  }

  .sc-lbl {
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .chart-section {
    background: var(--bg-surface);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    padding: 12px 14px;
  }

  .chart-title {
    font-size: 11px;
    font-weight: 600;
    color: var(--text-secondary);
    margin-bottom: 4px;
  }

  .chart-hint {
    font-size: 9px;
    color: var(--text-muted);
    font-style: italic;
    margin-bottom: 8px;
  }

  .section-hint {
    font-size: 10px;
    color: var(--text-muted);
    font-style: italic;
  }
  .section-hint code {
    font-size: 9px;
    font-family: var(--font-mono);
    background: var(--bg-inset);
    padding: 1px 4px;
    border-radius: 3px;
  }

  .bar-chart {
    display: flex;
    align-items: flex-end;
    gap: 2px;
    height: 80px;
    padding-bottom: 16px;
    position: relative;
  }

  .bar-col {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    height: 100%;
    justify-content: flex-end;
  }

  .bar {
    width: 100%;
    max-width: 20px;
    background: var(--accent-blue);
    border-radius: 2px 2px 0 0;
    min-height: 1px;
    transition: height 0.3s;
    opacity: 0.8;
  }

  .bar.dark {
    background: var(--accent-purple);
    opacity: 0.7;
  }

  .bar-date {
    position: absolute;
    bottom: 2px;
    font-size: 7px;
    color: var(--text-muted);
    white-space: nowrap;
    transform: translateY(14px);
  }

  .chart-legend {
    display: flex;
    gap: 14px;
    margin-top: 12px;
  }

  .legend-item {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 9px;
    color: var(--text-muted);
  }

  .legend-dot {
    width: 8px;
    height: 8px;
    border-radius: 2px;
    background: var(--accent-blue);
  }
  .legend-dot.dark { background: var(--accent-purple); }

  .two-col {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
  }

  .bar-list { display: flex; flex-direction: column; gap: 5px; }

  .bar-row {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .bar-label {
    font-size: 11px;
    color: var(--text-secondary);
    width: 90px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex-shrink: 0;
  }

  .bar-track {
    flex: 1;
    height: 5px;
    background: var(--bg-inset);
    border-radius: 3px;
    overflow: hidden;
  }

  .bar-fill {
    height: 100%;
    border-radius: 3px;
    transition: width 0.3s;
  }
  .bar-fill.blue { background: var(--accent-blue); }
  .bar-fill.purple { background: var(--accent-purple); }

  .bar-val {
    font-size: 10px;
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
    width: 60px;
    text-align: right;
    flex-shrink: 0;
  }

  .refresh-row {
    display: flex;
    justify-content: center;
  }

  .refresh-btn {
    display: flex;
    align-items: center;
    gap: 5px;
    padding: 6px 14px;
    font-size: 11px;
    color: var(--text-muted);
    border: 1px solid var(--border-muted);
    border-radius: var(--radius-sm);
    transition: background 0.12s;
  }
  .refresh-btn:hover {
    background: var(--bg-inset);
    color: var(--text-primary);
  }
</style>
