<script>
  import { SearchIcon } from '../../icons.js'
  import StatusDot from '../shared/StatusDot.svelte'
  import { fmtDur, fmtRel } from '../../utils/format.js'
  import { tasksStore } from '../../stores/tasksStore.svelte'
  import { ui } from '../../stores/uiStore.svelte'
  import { i18n, t } from '../../i18n/localeStore.svelte.ts'

  let query = $state('')
  let sortBy = $state('date')
  let statusFilter = $state('')

  let tasks = $derived(tasksStore.tasks)
  let selected = $derived(tasksStore.selected)

  let filtered = $derived.by(() => {
    let list = tasks
    if (query.trim()) {
      const q = query.toLowerCase()
      list = list.filter(t =>
        (t.agent ?? '').toLowerCase().includes(q) ||
        (t.model ?? '').toLowerCase().includes(q) ||
        (t.task_id ?? '').toLowerCase().includes(q) ||
        (t.executor ?? '').toLowerCase().includes(q)
      )
    }
    if (statusFilter) {
      list = list.filter(t => t.status === statusFilter)
    }
    const sorted = [...list]
    if (sortBy === 'cost') {
      sorted.sort((a, b) => (b.cost_usd ?? 0) - (a.cost_usd ?? 0))
    } else if (sortBy === 'duration') {
      sorted.sort((a, b) => (b.duration_ms ?? 0) - (a.duration_ms ?? 0))
    } else {
      sorted.sort((a, b) => (b._mtime ?? 0) - (a._mtime ?? 0))
    }
    return sorted
  })

  const sortOptions = $derived([
    { id: 'date',     label: t('sidebar.sortDate') },
    { id: 'cost',     label: t('sidebar.sortCost') },
    { id: 'duration', label: t('sidebar.sortDuration') },
  ])

  const statusOptions = $derived([
    { id: '',           label: t('sidebar.statusAll') },
    { id: 'completed',  label: t('sidebar.statusCompleted') },
    { id: 'failed',     label: t('sidebar.statusFailed') },
    { id: 'running',    label: t('sidebar.statusRunning') },
  ])
  void i18n.locale
</script>

<aside class="sidebar">
  <div class="sidebar-search">
    <SearchIcon size="13" strokeWidth="2" class="search-icon" />
    <input
      type="text"
      placeholder={t('sidebar.searchPlaceholder')}
      bind:value={query}
      class="search-input"
    />
  </div>

  <div class="sidebar-filters">
    <div class="filter-group">
      <select bind:value={sortBy} class="filter-select">
        {#each sortOptions as opt}
          <option value={opt.id}>{opt.label}</option>
        {/each}
      </select>
    </div>
    <div class="filter-group">
      <select bind:value={statusFilter} class="filter-select">
        {#each statusOptions as opt}
          <option value={opt.id}>{opt.label}</option>
        {/each}
      </select>
    </div>
  </div>

  <div class="task-count">
    {filtered.length} {t('sidebar.tasks', { n: filtered.length })}
    {#if tasks.length !== filtered.length}
      <span class="count-desc">{t('sidebar.of', { n: tasks.length })}</span>
    {/if}
  </div>

  <div class="task-list">
    {#each ui.activeRuns as run (run.id)}
      <div class="task-row task-row--running">
        <div class="task-row-top">
          <StatusDot status="running" size={7} />
          <span class="task-agent">{run.agent}</span>
          <span class="running-badge">{t('sidebar.running')}</span>
        </div>
        <div class="task-row-mid">
          <span class="task-model">{run.model}</span>
          {#if run.executor !== run.agent}
            <span class="task-executor">via {run.executor}</span>
          {/if}
        </div>
        <div class="task-row-bot">
          <span class="task-prompt">{run.task}</span>
        </div>
      </div>
    {/each}

    {#each filtered as task (task.task_id)}
      {@const isSelected = selected?.task_id === task.task_id}
      {@const isNew = tasksStore.isUnseen(task.task_id)}
      <button
        class="task-row"
        class:selected={isSelected}
        class:unseen={isNew}
        onclick={() => tasksStore.select(task)}
      >
        <div class="task-row-top">
          <StatusDot status={task.status} size={7} />
          <span class="task-agent">{task.agent ?? t('sidebar.unknown')}</span>
          {#if isNew}
            <span class="new-badge">new</span>
          {/if}
          <span class="task-cost" title={t('sidebar.costTitle')}>${(task.cost_usd ?? 0).toFixed(4)}</span>
        </div>
        <div class="task-row-mid">
          <span class="task-model">{task.model ?? '—'}</span>
          {#if task.executor && task.executor !== task.agent}
            <span class="task-executor">via {task.executor}</span>
          {/if}
        </div>
        <div class="task-row-bot">
          <span class="task-id">{(task.task_id ?? '').slice(0, 8)}</span>
          <span class="task-dur">{fmtDur(task.duration_ms)}</span>
          <span class="task-rel">{fmtRel(task._mtime)}</span>
        </div>
      </button>
    {/each}

    {#if filtered.length === 0 && ui.activeRuns.length === 0}
      <div class="empty">{t('sidebar.noTasks')}</div>
    {/if}
  </div>
</aside>

<style>
  .sidebar {
    width: 260px;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    background: var(--bg-surface);
    border-right: 1px solid var(--border-default);
    overflow: hidden;
  }

  .sidebar-search {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 10px;
    border-bottom: 1px solid var(--border-muted);
    color: var(--text-muted);
  }

  .search-input {
    flex: 1;
    background: none;
    border: none;
    outline: none;
    font-size: 12px;
    color: var(--text-primary);
  }

  .search-input::placeholder { color: var(--text-muted); }

  .sidebar-filters {
    display: flex;
    gap: 4px;
    padding: 4px 8px;
    border-bottom: 1px solid var(--border-muted);
  }

  .filter-group {
    flex: 1;
  }

  .filter-select {
    width: 100%;
    height: 24px;
    padding: 0 6px;
    background: var(--bg-inset);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    font-size: 10px;
    color: var(--text-secondary);
    outline: none;
    cursor: pointer;
    appearance: none;
  }
  .filter-select:focus { border-color: var(--accent-blue); }

  .task-count {
    padding: 3px 10px;
    font-size: 11px;
    color: var(--text-muted);
    border-bottom: 1px solid var(--border-muted);
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .count-desc {
    font-size: 10px;
    color: var(--text-muted);
    opacity: 0.6;
  }

  .task-list {
    flex: 1;
    overflow-y: auto;
  }

  .task-row {
    width: 100%;
    text-align: left;
    padding: 7px 10px;
    border-bottom: 1px solid var(--border-muted);
    display: flex;
    flex-direction: column;
    gap: 3px;
    cursor: pointer;
    transition: background 0.1s;
  }

  .task-row:hover { background: var(--bg-surface-hover); }
  .task-row.selected { background: var(--bg-inset); }

  .task-row-top {
    display: flex;
    align-items: center;
    gap: 5px;
  }

  .task-agent {
    font-size: 12px;
    font-weight: 500;
    color: var(--text-primary);
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .task-cost {
    font-size: 11px;
    font-variant-numeric: tabular-nums;
    color: var(--accent-amber);
    flex-shrink: 0;
  }

  .task-row-mid {
    display: flex;
    gap: 5px;
    align-items: center;
  }

  .task-model {
    font-size: 11px;
    color: var(--text-secondary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .task-executor {
    font-size: 10px;
    color: var(--text-muted);
    flex-shrink: 0;
  }

  .task-row-bot {
    display: flex;
    gap: 6px;
    align-items: center;
  }

  .task-id {
    font-family: var(--font-mono);
    font-size: 10px;
    color: var(--text-muted);
    flex: 1;
  }

  .task-dur, .task-rel {
    font-size: 10px;
    color: var(--text-muted);
    flex-shrink: 0;
  }

  .empty {
    padding: 24px 12px;
    text-align: center;
    font-size: 12px;
    color: var(--text-muted);
  }

  .task-row--running {
    cursor: default;
    border-left: 2px solid var(--running-fg, var(--accent-blue));
    background: color-mix(in srgb, var(--running-fg, var(--accent-blue)) 5%, transparent);
  }

  .running-badge {
    margin-left: auto;
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.03em;
    text-transform: uppercase;
    color: var(--running-fg, var(--accent-blue));
    animation: run-pulse 1.6s ease-in-out infinite;
    flex-shrink: 0;
  }

  @keyframes run-pulse { 0%,100%{opacity:1} 50%{opacity:0.35} }

  .task-prompt {
    font-size: 10px;
    color: var(--text-muted);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex: 1;
  }

  .unseen {
    border-left: 2px solid var(--accent-blue);
  }

  .new-badge {
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.03em;
    text-transform: uppercase;
    background: var(--accent-blue);
    color: var(--accent-blue-foreground, #fff);
    border-radius: 4px;
    padding: 0 4px;
    line-height: 14px;
    flex-shrink: 0;
  }
</style>
