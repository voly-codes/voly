<script>
  import { CoinsIcon, CpuIcon, ZapIcon, ClockIcon, ActivityIcon } from '../../icons.js'
  import { fmtTokens, fmtDur } from './lib/utils.js'

  let { costUsd = 0, inputTokens = 0, outputTokens = 0, savedTokens = 0, durationMs, routingScore, tokenBar = [] } = $props()
</script>

<div class="stats-strip">
  <div class="stat-card">
    <CoinsIcon size="12" strokeWidth="2" />
    <span class="stat-val">${costUsd.toFixed(5)}</span>
    <span class="stat-lbl">стоимость</span>
  </div>
  <div class="stat-card">
    <CpuIcon size="12" strokeWidth="2" />
    <span class="stat-val">{fmtTokens(inputTokens + outputTokens)}</span>
    <span class="stat-lbl">токенов</span>
  </div>
  {#if savedTokens > 0}
    <div class="stat-card saved">
      <ZapIcon size="12" strokeWidth="2" />
      <span class="stat-val">{fmtTokens(savedTokens)}</span>
      <span class="stat-lbl">сэкономлено</span>
    </div>
  {/if}
  <div class="stat-card">
    <ClockIcon size="12" strokeWidth="2" />
    <span class="stat-val">{fmtDur(durationMs)}</span>
    <span class="stat-lbl">время</span>
  </div>
  {#if routingScore}
    <div class="stat-card">
      <ActivityIcon size="12" strokeWidth="2" />
      <span class="stat-val">{(routingScore * 100).toFixed(0)}%</span>
      <span class="stat-lbl">routing</span>
    </div>
  {/if}
</div>

{#if tokenBar.length > 0}
  <div class="token-bar-wrap">
    <div class="token-bar">
      {#each tokenBar as seg}
        <div
          class="token-seg"
          style:width="{seg.pct}%"
          style:background={seg.color}
          title="{seg.label}: {seg.value.toLocaleString()} tokens ({seg.pct}%)"
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

<style>
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
</style>
