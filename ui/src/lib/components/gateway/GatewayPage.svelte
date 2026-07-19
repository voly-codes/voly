<script>
  // Gateway status dashboard: cache, rate, spend, fallback, DLP, errors,
  // provider/model breakdown bars. Metrics via GET /api/gateway/status.
  import { onMount } from 'svelte'
  import { AlertCircleIcon } from '../../icons.js'
  import { fetchGatewayStatus, fetchProviderHealth } from '../../api/client.js'
  import { t } from '../../i18n/localeStore.svelte.ts'
  import GatewayBreakdown from './GatewayBreakdown.svelte'
  import GatewayMetricCards from './GatewayMetricCards.svelte'
  import GatewayStatusBar from './GatewayStatusBar.svelte'
  import GatewayTotals from './GatewayTotals.svelte'

  let gw = $state(null)
  let health = $state(null)
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
</script>

<div class="gateway-page">
  {#if loading}
    <div class="loading">{t('gw.loading')}</div>

  {:else if error}
    <div class="error-block">
      <AlertCircleIcon size="16" strokeWidth="2" />
      <span>{error}</span>
      <button onclick={load}>{t('common.retry')}</button>
    </div>

  {:else if gw}
    <GatewayStatusBar {gw} onrefresh={load} />
    <GatewayMetricCards {gw} />
    <GatewayTotals metrics={gw.metrics} />
    <GatewayBreakdown metrics={gw.metrics} {health} />
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
</style>
