<script>
  import {
    RouteIcon, DatabaseIcon, ZapIcon, BookOpenIcon,
    LayersIcon, MessageSquareIcon, SaveIcon, BarChart2Icon,
    ChevronRightIcon,
  } from '../../icons.js'
  import { t } from '../../i18n/localeStore.svelte.ts'

  const stages = $derived([
    { icon: RouteIcon,         label: t('empty.route') },
    { icon: DatabaseIcon,      label: t('empty.memory') },
    { icon: ZapIcon,           label: t('empty.rtk') },
    { icon: BookOpenIcon,      label: t('empty.skills') },
    { icon: LayersIcon,        label: t('empty.headroom') },
    { icon: MessageSquareIcon, label: t('empty.model') },
    { icon: SaveIcon,          label: t('empty.store') },
    { icon: BarChart2Icon,     label: t('empty.telemetry') },
  ])
</script>

<div class="empty-state">
  <div class="empty-icon">
    <ChevronRightIcon size="28" strokeWidth="1.5" />
  </div>
  <p class="empty-title">{t('empty.title')}</p>
  <p class="empty-sub">{t('empty.sub')}</p>

  <div class="empty-flow">
    {#each stages as s, i}
      {@const Icon = s.icon}
      <div class="ef-step">
        <div class="ef-icon"><Icon size="12" strokeWidth="2" /></div>
        <span class="ef-label">{s.label}</span>
      </div>
      {#if i < stages.length - 1}
        <div class="ef-arrow">→</div>
      {/if}
    {/each}
  </div>
</div>

<style>
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 48px 24px;
    text-align: center;
    gap: 8px;
    height: 100%;
    color: var(--text-muted);
  }
  .empty-icon { opacity: 0.35; margin-bottom: 8px; }
  .empty-title {
    font-size: 14px;
    font-weight: 600;
    color: var(--text-secondary);
    margin: 0;
  }
  .empty-sub { font-size: 12px; margin: 0 0 20px; max-width: 280px; line-height: 1.4; }
  .empty-flow {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: center;
    gap: 4px;
    max-width: 420px;
  }
  .ef-step {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
  }
  .ef-icon {
    width: 28px;
    height: 28px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-default);
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-muted);
  }
  .ef-label { font-size: 9px; text-transform: uppercase; letter-spacing: 0.03em; }
  .ef-arrow { font-size: 11px; color: var(--text-muted); opacity: 0.5; margin-bottom: 14px; }
</style>
