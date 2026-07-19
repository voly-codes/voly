<script>
  import {
    AlertCircleIcon, CheckCircle2Icon, RefreshCwIcon,
  } from '../../icons.js'
  import { t } from '../../i18n/localeStore.svelte.ts'

  let { gw, onrefresh } = $props()
</script>

<div class="status-bar" class:enabled={gw.enabled} class:disabled={!gw.enabled}>
  {#if gw.enabled}
    <CheckCircle2Icon size="16" strokeWidth="2" />
    <span>{t('gw.active', { name: gw.provider + ' / ' + gw.gateway_id })}</span>
  {:else}
    <AlertCircleIcon size="16" strokeWidth="2" />
    <span>{t('gw.disabled')}</span>
  {/if}
  <button class="refresh-btn" onclick={onrefresh} title="Refresh">
    <RefreshCwIcon size="13" strokeWidth="2" />
  </button>
</div>

<style>
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
</style>
