<script>
  // Gateway status dashboard: cache, rate, spend, fallback, DLP, errors,
  // provider/model breakdown bars. Metrics via GET /api/gateway/status.
  import { onMount } from 'svelte'
  import {
    CoinsIcon, CpuIcon, DatabaseIcon, LockIcon,
    ClockIcon, ArrowDownWideNarrowIcon, AlertCircleIcon,
    CheckCircle2Icon, ZapIcon, LayersIcon, RefreshCwIcon,
  } from '../../icons.js'
  import { fetchGatewayStatus, fetchProviderHealth } from '../../api/client.js'
  import { fmtTokens } from '../../utils/format.js'

  let gw = $state(null)
  let health = $state<{ providers: Record<string, {healthy: boolean, reason: string}>, healthy: string[] } | null>(null)
  let loading = $state(true)
  let error = $state(null)

  async function load() {
    loading = true
    error = null
    try {
      ;[gw, health] = await Promise.all([fetchGatewayStatus(), fetchProviderHealth()])
    } catch (e) {
      error = e.message
    } finally {
      loading = false
    }
  }

  onMount(load)

  function cachePct() {
    const h = gw?.metrics?.cache_hits ?? 0
    const m = gw?.metrics?.cache_misses ?? 0
    const total = h + m
    if (!total) return 0
    return Math.round((h / total) * 100)
  }

  function spentPct() {
    const budget = gw?.spend_limit?.daily_budget_usd ?? 0
    const spent = gw?.spend_limit?.spent_today ?? 0
    if (!budget) return 0
    return Math.min(100, Math.round((spent / budget) * 100))
  }
</script>

<div class="gateway-page">
  {#if loading}
    <div class="loading">Загрузка статуса Gateway…</div>

  {:else if error}
    <div class="error-block">
      <AlertCircleIcon size="16" strokeWidth="2" />
      <span>{error}</span>
      <button onclick={load}>Повторить</button>
    </div>

  {:else if gw}
    <!-- Status banner -->
    <div class="status-bar" class:enabled={gw.enabled} class:disabled={!gw.enabled}>
      {#if gw.enabled}
        <CheckCircle2Icon size="16" strokeWidth="2" />
        <span>Gateway active — {gw.provider} / {gw.gateway_id}</span>
      {:else}
        <AlertCircleIcon size="16" strokeWidth="2" />
        <span>Gateway disabled</span>
      {/if}
      <button class="refresh-btn" onclick={load} title="Refresh">
        <RefreshCwIcon size="13" strokeWidth="2" />
      </button>
    </div>

    <div class="gw-grid">
      <!-- Cache -->
      <section class="gw-card">
        <div class="card-head">
          <DatabaseIcon size="14" strokeWidth="2" />
          <span>Cache</span>
          {#if gw.cache?.enabled}
            <span class="badge ok">on</span>
          {:else}
            <span class="badge muted">off</span>
          {/if}
        </div>
        <div class="card-body">
          <div class="kv"><span class="k">TTL</span><span class="v">{gw.cache?.ttl_seconds}s</span></div>
          <div class="kv"><span class="k">Max entries</span><span class="v">{gw.cache?.max_entries}</span></div>
          <div class="kv"><span class="k">Hit rate</span><span class="v acc">{cachePct()}%</span></div>
          <div class="bar-track" title="Hits: {gw.metrics?.cache_hits} · Misses: {gw.metrics?.cache_misses}">
            <div class="bar-fill green" style:width="{cachePct()}%"></div>
          </div>
          <div class="card-hint">Кэш ответов LLM. Попадание в кэш не тратит бюджет и ускоряет повторные запросы.</div>
        </div>
      </section>

      <!-- Rate Limits -->
      <section class="gw-card">
        <div class="card-head">
          <LayersIcon size="14" strokeWidth="2" />
          <span>Rate Limit</span>
          {#if gw.rate_limit?.enabled}
            <span class="badge ok">on</span>
          {:else}
            <span class="badge muted">off</span>
          {/if}
        </div>
        <div class="card-body">
          <div class="kv"><span class="k">Limit</span><span class="v">{gw.rate_limit?.requests_per_minute} rpm</span></div>
          <div class="kv"><span class="k">Current</span><span class="v">{gw.metrics?.rpm} rpm</span></div>
          <div class="kv"><span class="k">Rate limited</span><span class="v warn">{gw.metrics?.rate_limited}</span></div>
          <div class="card-hint">Защита от burst-нагрузки. При превышении RPM запросы блокируются до следующего окна.</div>
        </div>
      </section>

      <!-- Spend Limits -->
      <section class="gw-card">
        <div class="card-head">
          <CoinsIcon size="14" strokeWidth="2" />
          <span>Spend Limit</span>
          {#if gw.spend_limit?.enabled}
            <span class="badge ok">on</span>
          {:else}
            <span class="badge muted">off</span>
          {/if}
        </div>
        <div class="card-body">
          <div class="kv"><span class="k">Daily budget</span><span class="v">${gw.spend_limit?.daily_budget_usd?.toFixed(2)}</span></div>
          <div class="kv"><span class="k">Spent today</span><span class="v acc">${gw.spend_limit?.spent_today?.toFixed(4)}</span></div>
          <div class="bar-track" title="{spentPct()}% of daily budget">
            <div class="bar-fill amber" style:width="{spentPct()}%"></div>
          </div>
          <div class="card-hint">Дневной бюджет в USD. При превышении новые запросы отклоняются до сброса счётчика (24ч).</div>
        </div>
      </section>

      <!-- Fallback -->
      <section class="gw-card">
        <div class="card-head">
          <ArrowDownWideNarrowIcon size="14" strokeWidth="2" />
          <span>Fallback</span>
          {#if gw.fallback?.enabled}
            <span class="badge ok">on</span>
          {:else}
            <span class="badge muted">off</span>
          {/if}
        </div>
        <div class="card-body">
          <div class="kv"><span class="k">Retries</span><span class="v">{gw.fallback?.retries}</span></div>
          <div class="kv"><span class="k">Chain</span><span class="v">{gw.fallback?.chain?.length ?? 0} models</span></div>
          <div class="kv"><span class="k">Used</span><span class="v warn">{gw.metrics?.fallbacks_used}</span></div>
          {#if gw.fallback?.chain?.length}
            <div class="chain-list">
              {#each gw.fallback.chain as fb}
                <span class="chain-chip">{fb.provider}/{fb.model}</span>
              {/each}
            </div>
          {/if}
          <div class="card-hint">Цепочка резервных моделей при отказе основной. Каждая ошибка переключает на следующий элемент.</div>
        </div>
      </section>

      <!-- DLP -->
      <section class="gw-card">
        <div class="card-head">
          <LockIcon size="14" strokeWidth="2" />
          <span>DLP</span>
          {#if gw.dlp?.enabled}
            <span class="badge ok">on</span>
          {:else}
            <span class="badge muted">off</span>
          {/if}
        </div>
        <div class="card-body">
          <div class="kv"><span class="k">Block secrets</span><span class="v">{gw.dlp?.block_secrets ? 'yes' : 'no'}</span></div>
          <div class="kv"><span class="k">Block PII</span><span class="v">{gw.dlp?.block_pii ? 'yes' : 'no'}</span></div>
          <div class="kv"><span class="k">Blocks</span><span class="v err">{gw.metrics?.dlp_blocks}</span></div>
          <div class="card-hint">Блокирует secrets (API-ключи, JWT, SSH-ключи) и PII (email, SSN) до отправки в LLM.</div>
        </div>
      </section>

      <!-- Errors -->
      <section class="gw-card">
        <div class="card-head">
          <AlertCircleIcon size="14" strokeWidth="2" />
          <span>Errors</span>
        </div>
        <div class="card-body">
          <div class="big-num err">{gw.metrics?.errors}</div>
          <div class="big-label">total errors</div>
          <div class="card-hint">Общее количество ошибок при вызовах LLM (сетевые, таймауты, отказы провайдера).</div>
        </div>
      </section>
    </div>

    <!-- Totals row -->
    <div class="totals-row">
      <div class="total-chip">
        <ZapIcon size="13" strokeWidth="2" />
        <span class="total-val">{gw.metrics?.total_requests}</span>
        <span class="total-lbl">requests</span>
      </div>
      <div class="total-chip">
        <CpuIcon size="13" strokeWidth="2" />
        <span class="total-val">{fmtTokens(gw.metrics?.total_tokens)}</span>
        <span class="total-lbl">tokens</span>
      </div>
      <div class="total-chip">
        <CoinsIcon size="13" strokeWidth="2" />
        <span class="total-val">${gw.metrics?.total_cost_usd?.toFixed(4)}</span>
        <span class="total-lbl">total cost</span>
      </div>
      <div class="total-chip">
        <ClockIcon size="13" strokeWidth="2" />
        <span class="total-val">{gw.metrics?.rpm}</span>
        <span class="total-lbl">current rpm</span>
      </div>
    </div>

    <!-- Providers breakdown -->
    {#if Object.keys(gw.metrics?.by_provider ?? {}).length}
      <section class="breakdown-section">
        <div class="section-title">По провайдерам</div>
        <div class="bar-list">
          {#each Object.entries(gw.metrics.by_provider) as [prov, count]}
            {@const pct = gw.metrics.total_requests ? Math.round((count / gw.metrics.total_requests) * 100) : 0}
            <div class="bar-row">
              <span class="bar-label">{prov}</span>
              <div class="bar-track">
                <div class="bar-fill blue" style:width="{pct}%"></div>
              </div>
              <span class="bar-val">{count}</span>
            </div>
          {/each}
        </div>
      </section>
    {/if}

    <!-- Models breakdown -->
    {#if Object.keys(gw.metrics?.by_model ?? {}).length}
      <section class="breakdown-section">
        <div class="section-title">По моделям</div>
        <div class="bar-list">
          {#each Object.entries(gw.metrics.by_model) as [model, count]}
            {@const pct = gw.metrics.total_requests ? Math.round((count / gw.metrics.total_requests) * 100) : 0}
            <div class="bar-row">
              <span class="bar-label">{model}</span>
              <div class="bar-track">
                <div class="bar-fill purple" style:width="{pct}%"></div>
              </div>
              <span class="bar-val">{count}</span>
            </div>
          {/each}
        </div>
      </section>
    {/if}

    <!-- Provider Health -->
    {#if health}
      <section class="breakdown-section">
        <div class="breakdown-title">Провайдеры — состояние ключей</div>
        <div class="health-grid">
          {#each Object.entries(health.providers) as [prov, st]}
            <div class="health-row" class:healthy={st.healthy} class:unhealthy={!st.healthy}>
              <span class="health-dot" class:ok={st.healthy} class:err={!st.healthy}></span>
              <span class="health-name">{prov}</span>
              <span class="health-reason">{st.reason}</span>
            </div>
          {/each}
        </div>
        <div class="health-hint">
          Маршрутизатор обходит нездоровые провайдеры автоматически. Порядок приоритета:
          anthropic → workers-ai → deepseek → opencode-zen → mimo → google → openai
        </div>
      </section>
    {/if}
  {/if}
</div>

<style>
  .gateway-page {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 14px;
  }

  .loading {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
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
    cursor: pointer;
  }

  .status-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 14px;
    font-size: 13px;
    font-weight: 500;
    border-radius: var(--radius-md);
  }

  .status-bar.enabled {
    background: color-mix(in srgb, var(--accent-green) 12%, transparent);
    color: var(--accent-green);
    border: 1px solid color-mix(in srgb, var(--accent-green) 25%, transparent);
  }

  .status-bar.disabled {
    background: color-mix(in srgb, var(--accent-amber) 12%, transparent);
    color: var(--accent-amber);
    border: 1px solid color-mix(in srgb, var(--accent-amber) 25%, transparent);
  }

  .refresh-btn {
    margin-left: auto;
    width: 26px;
    height: 26px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--radius-sm);
    opacity: 0.7;
  }
  .refresh-btn:hover { opacity: 1; background: color-mix(in srgb, currentColor 12%, transparent); }

  .gw-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 10px;
  }

  .gw-card {
    background: var(--bg-surface);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    overflow: hidden;
  }

  .card-head {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 8px 12px;
    font-size: 12px;
    font-weight: 500;
    color: var(--text-primary);
    border-bottom: 1px solid var(--border-muted);
    background: var(--bg-inset);
  }

  .badge {
    margin-left: auto;
    font-size: 9px;
    font-weight: 600;
    text-transform: uppercase;
    padding: 1px 5px;
    border-radius: 3px;
  }
  .badge.ok { background: color-mix(in srgb, var(--accent-green) 20%, transparent); color: var(--accent-green); }
  .badge.muted { background: var(--bg-surface); color: var(--text-muted); }

  .card-body {
    padding: 10px 12px;
    display: flex;
    flex-direction: column;
    gap: 5px;
  }

  .card-hint {
    font-size: 9px;
    color: var(--text-muted);
    line-height: 1.4;
    margin-top: 2px;
    font-style: italic;
  }

  .kv {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    font-size: 11px;
  }

  .kv .k { color: var(--text-muted); }
  .kv .v { color: var(--text-secondary); font-variant-numeric: tabular-nums; }
  .kv .v.acc { color: var(--accent-amber); }
  .kv .v.warn { color: var(--accent-orange); }
  .kv .v.err { color: var(--accent-red); }

  .bar-track {
    height: 4px;
    background: var(--bg-inset);
    border-radius: 2px;
    overflow: hidden;
    margin-top: 2px;
  }

  .bar-fill {
    height: 100%;
    border-radius: 2px;
    transition: width 0.3s;
  }
  .bar-fill.green { background: var(--accent-green); }
  .bar-fill.amber { background: var(--accent-amber); }
  .bar-fill.blue { background: var(--accent-blue); }
  .bar-fill.purple { background: var(--accent-purple); }

  .big-num {
    font-size: 20px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    line-height: 1;
  }
  .big-num.err { color: var(--accent-red); }

  .big-label {
    font-size: 10px;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .chain-list {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-top: 2px;
  }

  .chain-chip {
    font-size: 9px;
    font-family: var(--font-mono);
    background: var(--bg-inset);
    border: 1px solid var(--border-muted);
    border-radius: var(--radius-sm);
    padding: 1px 5px;
    color: var(--text-muted);
  }

  .totals-row {
    display: flex;
    gap: 8px;
  }

  .total-chip {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    padding: 10px 8px;
    background: var(--bg-surface);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    color: var(--text-muted);
  }

  .total-val {
    font-size: 14px;
    font-weight: 600;
    color: var(--text-primary);
    font-variant-numeric: tabular-nums;
  }

  .total-lbl {
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .breakdown-section {
    padding: 12px 14px;
    background: var(--bg-surface);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
  }

  .section-title {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-muted);
    margin-bottom: 8px;
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
    width: 100px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex-shrink: 0;
  }

  .bar-val {
    font-size: 10px;
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
    width: 24px;
    text-align: right;
    flex-shrink: 0;
  }

  .health-grid { display: flex; flex-direction: column; gap: 4px; margin-top: 8px; }

  .health-row {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 11px;
    padding: 3px 6px;
    border-radius: var(--radius-sm);
  }
  .health-row.healthy  { background: color-mix(in srgb, var(--accent-green) 6%, transparent); }
  .health-row.unhealthy { background: color-mix(in srgb, var(--accent-red)   6%, transparent); }

  .health-dot {
    width: 7px; height: 7px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .health-dot.ok  { background: var(--accent-green); }
  .health-dot.err { background: var(--accent-red); }

  .health-name {
    width: 140px;
    flex-shrink: 0;
    font-weight: 500;
    color: var(--text-primary);
    font-size: 11px;
  }
  .health-reason { font-size: 10px; color: var(--text-muted); }

  .health-hint {
    margin-top: 8px;
    font-size: 10px;
    color: var(--text-muted);
    line-height: 1.5;
    opacity: 0.8;
  }
</style>
