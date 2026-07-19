<script>
  import { t } from '../../i18n/localeStore.svelte.ts'

  let { metrics, health = null } = $props()
</script>

<div class="breakdown-blocks">
  {#if Object.keys(metrics?.by_provider ?? {}).length}
    <section class="breakdown-section">
      <div class="section-title">{t('gw.byProvider')}</div>
      <div class="bar-list">
        {#each Object.entries(metrics.by_provider) as [prov, count]}
          {@const pct = metrics.total_requests ? Math.round((count / metrics.total_requests) * 100) : 0}
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

  {#if Object.keys(metrics?.by_model ?? {}).length}
    <section class="breakdown-section">
      <div class="section-title">{t('gw.byModel')}</div>
      <div class="bar-list">
        {#each Object.entries(metrics.by_model) as [model, count]}
          {@const pct = metrics.total_requests ? Math.round((count / metrics.total_requests) * 100) : 0}
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

  {#if health}
    <section class="breakdown-section">
      <div class="section-title">{t('gw.providerHealth')}</div>
      <div class="health-bricks">
        {#each Object.entries(health.providers) as [prov, st]}
          <div class="health-brick" class:healthy={st.healthy} class:unhealthy={!st.healthy}>
            <div class="brick-head">
              <span class="health-dot" class:ok={st.healthy} class:err={!st.healthy}></span>
              <span class="brick-name">{prov}</span>
            </div>
            <span class="brick-reason">{st.reason}</span>
          </div>
        {/each}
      </div>
      <div class="health-hint">
        {t('gw.healthHint')}
      </div>
    </section>
  {/if}
</div>

<style>
  .breakdown-blocks {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 10px;
  }

  .breakdown-section {
    padding: 12px 14px;
    background: var(--bg-surface);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    min-width: 0;
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

  .bar-track {
    flex: 1;
    height: 4px;
    background: var(--bg-inset);
    border-radius: 2px;
    overflow: hidden;
  }

  .bar-fill {
    height: 100%;
    border-radius: 2px;
    transition: width 0.3s;
  }
  .bar-fill.blue { background: var(--accent-blue); }
  .bar-fill.purple { background: var(--accent-purple); }

  .bar-val {
    font-size: 10px;
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
    width: 24px;
    text-align: right;
    flex-shrink: 0;
  }

  .health-bricks {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    gap: 6px;
    margin-top: 8px;
  }

  .health-brick {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 8px 10px;
    border-radius: var(--radius-md);
    border: 1px solid var(--border-default);
    background: var(--bg-inset);
  }
  .health-brick.healthy   { border-color: color-mix(in srgb, var(--accent-green) 30%, transparent); background: color-mix(in srgb, var(--accent-green) 7%, transparent); }
  .health-brick.unhealthy { border-color: color-mix(in srgb, var(--accent-red)   30%, transparent); background: color-mix(in srgb, var(--accent-red)   7%, transparent); }

  .brick-head { display: flex; align-items: center; gap: 6px; }

  .health-dot {
    width: 7px; height: 7px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .health-dot.ok  { background: var(--accent-green); }
  .health-dot.err { background: var(--accent-red); }

  .brick-name {
    font-weight: 600;
    color: var(--text-primary);
    font-size: 11px;
    font-family: var(--font-mono);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .brick-reason { font-size: 9px; color: var(--text-muted); line-height: 1.3; }

  .health-hint {
    margin-top: 8px;
    font-size: 10px;
    color: var(--text-muted);
    line-height: 1.5;
    opacity: 0.8;
  }
</style>
