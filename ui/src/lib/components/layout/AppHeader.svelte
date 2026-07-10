<script>
  import { MoonIcon, SunIcon, ActivityIcon } from '../../icons.js'
  import { theme } from '../../stores/themeStore.svelte.ts'
  import { i18n, t } from '../../i18n/localeStore.svelte.ts'

  let { taskCount = 0, totalCost = 0 } = $props()
</script>

<header class="app-header">
  <div class="brand">
    <ActivityIcon size="16" strokeWidth="2" />
    <span class="brand-name">VOLY</span>
  </div>

  <div class="header-stats">
    <span class="stat">
      <span class="stat-value">{taskCount}</span>
      <span class="stat-label">{t('header.tasks')}</span>
    </span>
    <span class="stat-divider"></span>
    <span class="stat">
      <span class="stat-value">${totalCost.toFixed(4)}</span>
      <span class="stat-label">{t('header.totalCost')}</span>
    </span>
  </div>

  <div class="header-actions">
    <div class="lang-switch" role="group" aria-label={t('header.switchLang')}>
      <button
        class="lang-btn"
        class:active={i18n.locale === 'en'}
        onclick={() => i18n.set('en')}
        title="English"
      >{t('header.langEn')}</button>
      <button
        class="lang-btn"
        class:active={i18n.locale === 'ru'}
        onclick={() => i18n.set('ru')}
        title="Русский"
      >{t('header.langRu')}</button>
    </div>

    <button class="icon-btn" onclick={() => theme.toggle()} title={t('header.toggleTheme')}>
      {#if theme.dark}
        <SunIcon size="14" strokeWidth="2" />
      {:else}
        <MoonIcon size="14" strokeWidth="2" />
      {/if}
    </button>
  </div>
</header>

<style>
  .app-header {
    height: var(--header-height);
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 0 12px;
    background: var(--bg-surface);
    border-bottom: 1px solid var(--border-default);
    flex-shrink: 0;
    z-index: 10;
  }

  .brand {
    display: flex;
    align-items: center;
    gap: 6px;
    color: var(--text-primary);
    font-weight: 600;
    font-size: 13px;
    flex-shrink: 0;
  }

  .brand-name { letter-spacing: -0.01em; }

  .header-stats {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-left: 8px;
    flex: 1;
  }

  .stat {
    display: flex;
    align-items: baseline;
    gap: 4px;
  }

  .stat-value {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-primary);
    font-variant-numeric: tabular-nums;
  }

  .stat-label {
    font-size: 10px;
    color: var(--text-muted);
  }

  .stat-divider {
    width: 1px;
    height: 14px;
    background: var(--border-default);
  }

  .header-actions {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .lang-switch {
    display: flex;
    gap: 2px;
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    padding: 2px;
    background: var(--bg-inset, transparent);
  }
  .lang-btn {
    background: none;
    border: none;
    border-radius: 3px;
    padding: 2px 7px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.04em;
    color: var(--text-muted);
    cursor: pointer;
    font-family: var(--font-mono, monospace);
  }
  .lang-btn:hover { color: var(--text-primary); }
  .lang-btn.active {
    color: var(--text-primary);
    background: var(--bg-surface);
    box-shadow: 0 0 0 1px var(--border-default);
  }

  .icon-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    background: none;
    color: var(--text-secondary);
    cursor: pointer;
  }
  .icon-btn:hover { color: var(--text-primary); }
</style>
