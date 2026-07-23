<script>
  import {
    RouteIcon, DatabaseIcon, ZapIcon, BookOpenIcon,
    LayersIcon, MessageSquareIcon, SaveIcon, BarChart2Icon,
  } from '../../icons.js'
  import { t } from '../../i18n/localeStore.svelte.ts'
  import PixelGoose from '../shared/PixelGoose.svelte'

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
    <PixelGoose size={34} />
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
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 48px 24px;
    text-align: center;
    gap: 8px;
    color: var(--text-muted);
    margin: 20px;
    border: 3px solid var(--frame-strong);
    background-color: color-mix(in srgb, var(--voly-paper) 18%, var(--bg-surface));
    background-image: conic-gradient(from 90deg at 3px 3px, color-mix(in srgb, var(--voly-orange) 20%, transparent) 25%, transparent 0);
    background-size: 16px 16px;
    box-shadow: 7px 7px 0 color-mix(in srgb, var(--voly-orange) 76%, transparent);
  }
  .empty-icon { margin-bottom: 8px; padding: 7px 10px 5px; border: 3px solid var(--voly-orange); background: var(--bg-surface); box-shadow: 4px 4px 0 color-mix(in srgb, var(--voly-ink) 42%, transparent); }
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
    border-radius: 0;
    border: 2px solid var(--border-default);
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--voly-orange);
    background: var(--bg-surface);
  }
  .ef-label { font-size: 9px; text-transform: uppercase; letter-spacing: 0.03em; }
  .ef-arrow { font-size: 11px; color: var(--text-muted); opacity: 0.5; margin-bottom: 14px; }
</style>
