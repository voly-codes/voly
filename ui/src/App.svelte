<script>
  import { onMount } from 'svelte'
  import AppHeader from './lib/components/layout/AppHeader.svelte'
  import TaskSidebar from './lib/components/tasks/TaskSidebar.svelte'
  import PipelineInspector from './lib/components/tasks/PipelineInspector.svelte'
  import CostPanel from './lib/components/tasks/CostPanel.svelte'
  import RunPanel from './lib/components/tasks/RunPanel.svelte'
  import MarketplacePage from './lib/components/cf/MarketplacePage.svelte'
  import CFPage from './lib/components/cf/CFPage.svelte'
  import DSPyPage from './lib/components/dspy/DSPyPage.svelte'
  import Drawer from './lib/components/shared/Drawer.svelte'
  import { PlayIcon, CloudUploadIcon, BookOpenIcon } from './lib/icons.js'
  import { fetchTasks, fetchSummary, fetchStatus } from './lib/api/client.js'

  let dark = $state(false)
  let page = $state('tasks')   // 'tasks' | 'dspy'

  let tasks = $state([])
  let selected = $state(null)
  let summary = $state(null)
  let status = $state(null)
  let loading = $state(true)
  let error = $state(null)

  // Drawers
  let runOpen       = $state(false)
  let cfOpen        = $state(false)
  let marketOpen    = $state(false)

  const navItems = [
    { id: 'tasks', label: 'Tasks' },
    { id: 'dspy',  label: 'DSPy' },
  ]

  const drawerBtns = [
    { open: () => runOpen    = true, icon: PlayIcon,        label: 'Run' },
    { open: () => cfOpen     = true, icon: CloudUploadIcon, label: 'CF' },
    { open: () => marketOpen = true, icon: BookOpenIcon,    label: 'Skills' },
  ]

  $effect(() => {
    document.documentElement.classList.toggle('dark', dark)
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

  <nav class="nav">
    <div class="nav-left">
      {#each navItems as item}
        <button
          class="nav-btn"
          class:active={page === item.id}
          onclick={() => page = item.id}
        >{item.label}</button>
      {/each}
    </div>

    <div class="nav-right">
      {#each drawerBtns as btn}
        {@const Icon = btn.icon}
        <button class="drawer-trigger" onclick={btn.open} title={btn.label}>
          <Icon size="13" strokeWidth="2" />
          <span>{btn.label}</span>
        </button>
      {/each}
    </div>
  </nav>

  {#if error && page === 'tasks'}
    <div class="error-banner">
      Нет соединения с CodeOps API: {error}
      <button onclick={load}>Повторить</button>
    </div>
  {/if}

  <div class="body">
    {#if page === 'tasks'}
      {#if loading && tasks.length === 0}
        <div class="loading">Загрузка задач…</div>
      {:else}
        <TaskSidebar {tasks} bind:selected />
        <main class="main">
          <PipelineInspector task={selected} />
        </main>
        <CostPanel {summary} task={selected} />
      {/if}

    {:else if page === 'dspy'}
      <DSPyPage />
    {/if}
  </div>
</div>

<!-- Drawers -->
<Drawer bind:open={runOpen} title="Запустить задачу" width="480px">
  <RunPanel onTaskComplete={() => { runOpen = false; load() }} />
</Drawer>

<Drawer bind:open={cfOpen} title="Cloudflare" width="520px">
  <CFPage />
</Drawer>

<Drawer bind:open={marketOpen} title="Skill Marketplace" width="600px">
  <MarketplacePage />
</Drawer>

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
    flex-shrink: 0;
  }

  .error-banner button {
    padding: 2px 10px;
    border: 1px solid currentColor;
    border-radius: var(--radius-sm);
    font-size: 11px;
  }

  .nav {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 12px;
    height: 36px;
    background: var(--bg-surface);
    border-bottom: 1px solid var(--border-default);
    flex-shrink: 0;
  }

  .nav-left {
    display: flex;
    align-items: center;
    gap: 2px;
  }

  .nav-right {
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .nav-btn {
    height: 26px;
    padding: 0 10px;
    font-size: 12px;
    font-weight: 500;
    border-radius: var(--radius-sm);
    color: var(--text-muted);
    background: transparent;
    transition: background 0.12s, color 0.12s;
  }

  .nav-btn:hover {
    background: var(--bg-inset);
    color: var(--text-primary);
  }

  .nav-btn.active {
    background: var(--bg-inset);
    color: var(--text-primary);
  }

  .drawer-trigger {
    height: 26px;
    padding: 0 9px;
    font-size: 11px;
    font-weight: 500;
    border-radius: var(--radius-sm);
    color: var(--text-muted);
    background: transparent;
    display: flex;
    align-items: center;
    gap: 5px;
    border: 1px solid var(--border-muted);
    transition: background 0.12s, color 0.12s, border-color 0.12s;
  }

  .drawer-trigger:hover {
    background: var(--bg-inset);
    color: var(--text-primary);
    border-color: var(--border-default);
  }
</style>
