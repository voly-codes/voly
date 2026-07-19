<script>
  import {
    CoinsIcon, DatabaseIcon, LockIcon,
    ArrowDownWideNarrowIcon, AlertCircleIcon, LayersIcon,
  } from '../../icons.js'
  import { t } from '../../i18n/localeStore.svelte.ts'

  let { gw } = $props()

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

<div class="gw-grid">
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
      <div class="card-hint">{t('gw.cacheHint')}</div>
    </div>
  </section>

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
      <div class="card-hint">{t('gw.rateHint')}</div>
    </div>
  </section>

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
      <div class="card-hint">{t('gw.spendHint')}</div>
    </div>
  </section>

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
      <div class="card-hint">{t('gw.fallbackHint')}</div>
    </div>
  </section>

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
      <div class="card-hint">{t('gw.dlpHint')}</div>
    </div>
  </section>

  <section class="gw-card">
    <div class="card-head">
      <AlertCircleIcon size="14" strokeWidth="2" />
      <span>Errors</span>
    </div>
    <div class="card-body">
      <div class="big-num err">{gw.metrics?.errors}</div>
      <div class="big-label">total errors</div>
      <div class="card-hint">{t('gw.errorsHint')}</div>
    </div>
  </section>
</div>

<style>
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
</style>
