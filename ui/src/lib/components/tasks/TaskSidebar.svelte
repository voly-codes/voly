<script>
  import { SearchIcon } from '../../icons.js'
  import StatusDot from '../shared/StatusDot.svelte'

  let { tasks = [], selected = $bindable(null), onselect } = $props()

  let query = $state('')

  let filtered = $derived(
    query.trim()
      ? tasks.filter(t =>
          (t.agent ?? '').includes(query) ||
          (t.model ?? '').includes(query) ||
          (t.task_id ?? '').includes(query) ||
          (t.executor ?? '').includes(query)
        )
      : tasks
  )

  function select(task) {
    selected = task
    onselect?.(task)
  }

  function fmt(ms) {
    if (!ms) return '—'
    if (ms < 1000) return `${Math.round(ms)}ms`
    return `${(ms / 1000).toFixed(1)}s`
  }

  function rel(mtime) {
    if (!mtime) return ''
    const d = new Date(mtime * 1000)
    const diff = (Date.now() - d) / 1000
    if (diff < 60) return 'just now'
    if (diff < 3600) return `${Math.round(diff / 60)}m ago`
    if (diff < 86400) return `${Math.round(diff / 3600)}h ago`
    return d.toLocaleDateString()
  }
</script>

<aside class="sidebar">
  <div class="sidebar-search">
    <SearchIcon size="13" strokeWidth="2" class="search-icon" />
    <input
      type="text"
      placeholder="Filter tasks…"
      bind:value={query}
      class="search-input"
    />
  </div>

  <div class="task-count">{filtered.length} tasks</div>

  <div class="task-list">
    {#each filtered as task (task.task_id)}
      {@const isSelected = selected?.task_id === task.task_id}
      <button
        class="task-row"
        class:selected={isSelected}
        onclick={() => select(task)}
      >
        <div class="task-row-top">
          <StatusDot status={task.status} size={7} />
          <span class="task-agent">{task.agent ?? 'unknown'}</span>
          <span class="task-cost">${(task.cost_usd ?? 0).toFixed(4)}</span>
        </div>
        <div class="task-row-mid">
          <span class="task-model">{task.model ?? '—'}</span>
          {#if task.executor && task.executor !== task.agent}
            <span class="task-executor">via {task.executor}</span>
          {/if}
        </div>
        <div class="task-row-bot">
          <span class="task-id">{(task.task_id ?? '').slice(0, 8)}</span>
          <span class="task-dur">{fmt(task.duration_ms)}</span>
          <span class="task-rel">{rel(task._mtime)}</span>
        </div>
      </button>
    {/each}

    {#if filtered.length === 0}
      <div class="empty">No tasks found</div>
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
    padding: 8px 10px;
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

  .task-count {
    padding: 4px 10px;
    font-size: 11px;
    color: var(--text-muted);
    border-bottom: 1px solid var(--border-muted);
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
</style>
