<script>
  import {
    RouteIcon, DatabaseIcon, ZapIcon, BookOpenIcon,
    LayersIcon, MessageSquareIcon, SaveIcon, BarChart2Icon,
    ChevronRightIcon,
  } from '../../icons.js'

  const stages = [
    { icon: RouteIcon,        label: 'Маршрут' },
    { icon: DatabaseIcon,     label: 'Память' },
    { icon: ZapIcon,          label: 'RTK' },
    { icon: BookOpenIcon,     label: 'Скилы' },
    { icon: LayersIcon,       label: 'Headroom' },
    { icon: MessageSquareIcon,label: 'Модель' },
    { icon: SaveIcon,         label: 'Запись' },
    { icon: BarChart2Icon,    label: 'Телеметрия' },
  ]
</script>

<div class="empty-state">
  <div class="empty-icon">
    <ChevronRightIcon size="28" strokeWidth="1.5" />
  </div>
  <p class="empty-title">Выберите задачу для инспекции</p>
  <p class="empty-sub">Детали pipeline, токены, расходы и стадии выполнения</p>

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
    gap: 8px;
    color: var(--text-muted);
    padding: 32px;
  }

  .empty-icon { color: var(--border-default); }

  .empty-title {
    font-size: 13px;
    font-weight: 500;
    color: var(--text-secondary);
    margin: 0;
  }

  .empty-sub {
    font-size: 11px;
    color: var(--text-muted);
    margin: 0 0 16px;
  }

  .empty-flow {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 4px;
    justify-content: center;
    max-width: 480px;
  }

  .ef-step {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 3px;
  }

  .ef-icon {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background: var(--bg-inset);
    border: 1px solid var(--border-muted);
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-muted);
  }

  .ef-label {
    font-size: 9px;
    color: var(--text-muted);
    white-space: nowrap;
  }

  .ef-arrow {
    font-size: 11px;
    color: var(--border-default);
    margin-bottom: 12px;
  }
</style>
