<script>
  import { onMount } from 'svelte'
  import { CheckIcon, AlertCircleIcon, CoinsIcon } from '../../icons.js'
  import { fetchCFWorkersStatus, fetchCFSpend } from '../../api/client.js'

  let workers = $state({})
  let spend = $state(null)
  let spendDays = $state(7)
  let loadingWorkers = $state(true)
  let loadingSpend = $state(false)
  let spendError = $state('')

  onMount(async () => {
    try { workers = await fetchCFWorkersStatus() } catch {}
    loadingWorkers = false
    await loadSpend()
  })

  async function loadSpend() {
    loadingSpend = true
    spendError = ''
    try { spend = await fetchCFSpend(spendDays) }
    catch (e) { spendError = e.message }
    finally { loadingSpend = false }
  }

  $effect(() => {
    spendDays
    loadSpend()
  })

  const workerNames = {
    spend:       'Spend Tracker',
    marketplace: 'Skill Marketplace',
    agui:        'AG-UI Gateway',
    memory:      'Memory Store',
    a2a:         'A2A Federation',
    workflow:    'Workflow Engine',
    catalog:     'Model Catalog',
    telemetry:   'Telemetry Ingest',
  }

  const workerHints = {
    spend:       'Tracks AI API spend per agent using Durable Objects. Provides daily breakdown and agent-level cost attribution.',
    marketplace: 'Serves skill definitions from D1 + R2. Supports FTS and semantic search via Vectorize. Skills are installed from here into .codeops/skills/.',
    agui:        'AG-UI protocol gateway. Streams agent events (text deltas, tool calls, state updates) to the frontend in real time.',
    memory:      'Semantic memory store. Embeds task results via Workers AI and stores them in Vectorize + D1 for future context retrieval.',
    a2a:         'Agent-to-Agent federation layer. Discovers specialized sub-agents and delegates tasks to the best match.',
    workflow:    'Multi-step workflow engine with human-in-the-loop approval gates, parallel branches, and checkpoint/resume support.',
    catalog:     'Model catalog and router. Lists available models, their costs, and selects the optimal one for each task.',
    telemetry:   'Ingest worker for pipeline events. Records cost, tokens, duration, and stage data for observability and analytics.',
  }

  function statusColor(configured) {
    return configured ? 'var(--accent-green)' : 'var(--border-default)'
  }
</script>

<div class="cf-page">
  <!-- Workers status -->
  <section class="cf-section">
    <div class="section-header">
      <span class="section-title">Cloudflare Workers</span>
      <span class="section-sub">Зелёный — подключён, серый — не настроен</span>
    </div>
    <p class="section-desc">Каждый воркер — отдельный Cloudflare Worker. Укажи URL в .env (напр. <code>CF_WORKER_MARKETPLACE_URL</code>) чтобы подключить его к CodeOps.</p>

    {#if loadingWorkers}
      <div class="loading-text">Загрузка…</div>
    {:else}
      <div class="workers-grid">
        {#each Object.entries(workers) as [key, w]}
          <div class="worker-card" class:active={w.configured}>
            <div class="worker-dot" style:background={statusColor(w.configured)}></div>
            <div class="worker-info">
              <div class="worker-name">{workerNames[key] ?? key}</div>
              {#if workerHints[key]}
                <div class="worker-hint">{workerHints[key]}</div>
              {/if}
              {#if w.configured}
                <div class="worker-url">{w.url}</div>
              {:else}
                <div class="worker-env">{w.env_key}</div>
              {/if}
            </div>
            <div class="worker-status">
              {#if w.configured}
                <CheckIcon size="12" strokeWidth="2.5" style="color: var(--accent-green)" />
              {:else}
                <span class="not-set">не задан</span>
              {/if}
            </div>
          </div>
        {/each}
      </div>
    {/if}
  </section>

  <!-- Spend tracking -->
  <section class="cf-section">
    <div class="section-header">
      <span class="section-title">
        <CoinsIcon size="13" strokeWidth="2" />
        CF Spend Tracker
      </span>
      <div class="days-select">
        {#each [1, 7, 30] as d}
          <button
            class="day-btn"
            class:active={spendDays === d}
            onclick={() => spendDays = d}
          >{d}d</button>
        {/each}
      </div>
    </div>

    <p class="section-desc">AI API расходы по агентам через Durable Objects. Данные накапливаются в реальном времени. Установи <code>CF_WORKER_SPEND_URL</code> для подключения.</p>

    {#if loadingSpend}
      <div class="loading-text">Загрузка расходов…</div>
    {:else if spendError}
      <div class="spend-error">
        <AlertCircleIcon size="13" strokeWidth="2" />
        {spendError}
      </div>
    {:else if spend && !spend.configured}
      <div class="not-configured-msg">
        <AlertCircleIcon size="14" strokeWidth="2" />
        <div>
          <div>{spend.hint ?? 'CF Spend Worker not configured'}</div>
          <code class="env-hint">CF_WORKER_SPEND_URL=https://codeops-spend.*.workers.dev</code>
        </div>
      </div>
    {:else if spend}
      <div class="spend-summary">
        <div class="spend-total">
          <span class="spend-val">${(spend.total ?? 0).toFixed(4)}</span>
          <span class="spend-label">за {spendDays} дн.</span>
        </div>

        {#if spend.agents?.length}
          <div class="spend-agents">
            {#each spend.agents as row}
              <div class="agent-spend-row">
                <span class="agent-name">{row.agent ?? row.name ?? '—'}</span>
                <div class="agent-bar-wrap">
                  <div
                    class="agent-bar"
                    style:width="{spend.total ? Math.round((row.total ?? row.cost ?? 0) / spend.total * 100) : 0}%"
                  ></div>
                </div>
                <span class="agent-cost">${(row.total ?? row.cost ?? 0).toFixed(4)}</span>
              </div>
            {/each}
          </div>
        {/if}

        {#if spend.daily}
          <div class="daily-title">По дням</div>
          <div class="daily-chart">
            {#each spend.daily as day}
              {@const max = Math.max(...spend.daily.map(d => d.total ?? 0), 0.001)}
              <div class="day-col">
                <div class="day-bar-wrap">
                  <div
                    class="day-bar"
                    style:height="{Math.round(((day.total ?? 0) / max) * 60)}px"
                    title="${(day.total ?? 0).toFixed(4)}"
                  ></div>
                </div>
                <span class="day-label">{(day.date ?? '').slice(-5)}</span>
              </div>
            {/each}
          </div>
        {/if}
      </div>
    {/if}
  </section>
</div>

<style>
  .cf-page {
    flex: 1;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 0;
  }

  .cf-section {
    padding: 14px 16px;
    border-bottom: 1px solid var(--border-default);
  }

  .section-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 12px;
  }

  .section-title {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-primary);
    display: flex;
    align-items: center;
    gap: 5px;
    flex: 1;
  }

  .section-sub {
    font-size: 11px;
    color: var(--text-muted);
  }

  .workers-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 6px;
  }

  .worker-card {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    padding: 8px 10px;
    background: var(--bg-inset);
    border: 1px solid var(--border-muted);
    border-radius: var(--radius-sm);
    opacity: 0.6;
    transition: opacity 0.15s;
  }
  .worker-card.active { opacity: 1; }

  .worker-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    flex-shrink: 0;
    margin-top: 4px;
  }

  .worker-info { flex: 1; min-width: 0; }

  .section-desc {
    font-size: 11px;
    color: var(--text-muted);
    line-height: 1.5;
    margin: 0 0 10px;
  }

  .section-desc code {
    font-family: var(--font-mono);
    font-size: 10px;
    background: var(--bg-inset);
    padding: 1px 4px;
    border-radius: 3px;
    color: var(--text-secondary);
  }

  .worker-name {
    font-size: 12px;
    font-weight: 500;
    color: var(--text-primary);
  }

  .worker-hint {
    font-size: 10px;
    color: var(--text-muted);
    line-height: 1.4;
    margin-top: 2px;
  }

  .worker-url {
    font-size: 10px;
    color: var(--text-muted);
    font-family: var(--font-mono);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    margin-top: 2px;
  }

  .worker-env {
    font-size: 10px;
    color: var(--text-muted);
    font-family: var(--font-mono);
    margin-top: 2px;
  }

  .worker-status { flex-shrink: 0; }
  .not-set { font-size: 10px; color: var(--text-muted); }

  .loading-text { font-size: 12px; color: var(--text-muted); padding: 4px 0; }

  .days-select { display: flex; gap: 2px; }

  .day-btn {
    height: 22px;
    padding: 0 8px;
    font-size: 11px;
    background: var(--bg-inset);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    color: var(--text-muted);
  }
  .day-btn.active { background: var(--accent-blue); color: var(--accent-blue-foreground); border-color: var(--accent-blue); }

  .not-configured-msg {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    color: var(--accent-amber);
    font-size: 12px;
  }
  .env-hint { display: block; font-size: 10px; color: var(--text-muted); margin-top: 4px; }

  .spend-error {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: var(--accent-red);
  }

  .spend-summary { display: flex; flex-direction: column; gap: 12px; }

  .spend-total {
    display: flex;
    align-items: baseline;
    gap: 8px;
  }
  .spend-val { font-size: 24px; font-weight: 700; color: var(--text-primary); font-variant-numeric: tabular-nums; }
  .spend-label { font-size: 12px; color: var(--text-muted); }

  .spend-agents { display: flex; flex-direction: column; gap: 6px; }

  .agent-spend-row { display: flex; align-items: center; gap: 8px; }
  .agent-name { width: 80px; font-size: 11px; color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex-shrink: 0; }
  .agent-bar-wrap { flex: 1; height: 4px; background: var(--bg-inset); border-radius: 2px; overflow: hidden; }
  .agent-bar { height: 100%; background: var(--accent-amber); border-radius: 2px; transition: width 0.3s; }
  .agent-cost { font-size: 11px; color: var(--text-muted); font-variant-numeric: tabular-nums; width: 60px; text-align: right; flex-shrink: 0; }

  .daily-title { font-size: 11px; color: var(--text-muted); font-weight: 500; }

  .daily-chart {
    display: flex;
    align-items: flex-end;
    gap: 4px;
    height: 80px;
  }

  .day-col {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 3px;
    flex: 1;
  }

  .day-bar-wrap {
    flex: 1;
    width: 100%;
    display: flex;
    align-items: flex-end;
  }

  .day-bar {
    width: 100%;
    background: var(--accent-blue);
    border-radius: var(--radius-sm) var(--radius-sm) 0 0;
    min-height: 2px;
    transition: height 0.3s;
  }

  .day-label {
    font-size: 9px;
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
  }
</style>
