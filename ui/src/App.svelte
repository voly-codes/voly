<script>
  import { onMount } from 'svelte'
  import AppHeader from './lib/components/layout/AppHeader.svelte'
  import TaskSidebar from './lib/components/tasks/TaskSidebar.svelte'
  import PipelineInspector from './lib/components/tasks/PipelineInspector.svelte'
  import CostPanel from './lib/components/tasks/CostPanel.svelte'
  import { fetchTasks, fetchSummary, fetchStatus } from './lib/api/client.js'

  let dark = $state(false)
  let tasks = $state([])
  let selected = $state(null)
  let summary = $state(null)
  let status = $state(null)
  let loading = $state(true)
  let error = $state(null)

  $effect(() => {
    if (dark) {
      document.documentElement.classList.add('dark')
    } else {
      document.documentElement.classList.remove('dark')
    }
  })

  async function load() {
    try {
      const [t, s, st] = await Promise.all([fetchTasks(), fetchSummary(), fetchStatus()])
      tasks = t
      summary = s
      status = st
      error = null
    } catch (e) {
      error = e.message
    } finally {
      loading = false
    }
  }

  onMount(() => {
    load()
    const iv = setInterval(load, 10_000)
    return () => clearInterval(iv)
  })
</script>

<div class="app">
  <AppHeader
    bind:dark
    taskCount={status?.tasks_count ?? tasks.length}
    totalCost={summary?.total_cost_usd ?? 0}
  />

  {#if loading && tasks.length === 0}
    <div class="loading">Loading tasks…</div>
  {:else if error}
    <div class="error-banner">
      Failed to connect to CodeOps API: {error}
      <button onclick={load}>Retry</button>
    </div>
  {:else}
    <div class="body">
      <TaskSidebar {tasks} bind:selected />

      <main class="main">
        <PipelineInspector task={selected} />
      </main>

      <CostPanel {summary} task={selected} />
    </div>
  {/if}
</div>

<style>
  .app {
    height: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .body {
    flex: 1;
    display: flex;
    overflow: hidden;
  }

  .main {
    flex: 1;
    display: flex;
    overflow: hidden;
    background: var(--bg-primary);
  }

  .loading {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 13px;
    color: var(--text-muted);
  }

  .error-banner {
    padding: 10px 16px;
    background: color-mix(in srgb, var(--accent-red) 10%, transparent);
    color: var(--accent-red);
    border-bottom: 1px solid color-mix(in srgb, var(--accent-red) 30%, transparent);
    font-size: 12px;
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .error-banner button {
    padding: 2px 10px;
    border: 1px solid currentColor;
    border-radius: var(--radius-sm);
    font-size: 11px;
  }
</style>
