<script lang="ts">
  import { onMount } from 'svelte'
  import AppHeader from './lib/components/layout/AppHeader.svelte'
  import TaskSidebar from './lib/components/tasks/TaskSidebar.svelte'
  import PipelineInspector from './lib/components/tasks/PipelineInspector.svelte'
  import CostPanel from './lib/components/tasks/CostPanel.svelte'
  import RunPanel from './lib/components/tasks/RunPanel.svelte'
  import MarketplacePage from './lib/components/cf/MarketplacePage.svelte'
  import PluginsPage from './lib/components/cf/PluginsPage.svelte'
  import CFPage from './lib/components/cf/CFPage.svelte'
  import DSPyPage from './lib/components/dspy/DSPyPage.svelte'
  import GatewayPage from './lib/components/gateway/GatewayPage.svelte'
  import TelemetryPage from './lib/components/telemetry/TelemetryPage.svelte'
  import Drawer from './lib/components/shared/Drawer.svelte'
  import Toast from './lib/components/shared/Toast.svelte'
  import Spinner from './lib/components/shared/Spinner.svelte'
  import { PlayIcon, CloudUploadIcon, BookOpenIcon } from './lib/icons.js'
  import { tasksStore } from './lib/stores/tasksStore.svelte'
  import { ui } from './lib/stores/uiStore.svelte'
  import { toast } from './lib/stores/toastStore.svelte'
  import { router } from './lib/stores/routerStore.svelte'
  import { registerShortcuts, global } from './lib/utils/keyboard.js'
  import { i18n, t } from './lib/i18n/localeStore.svelte.ts'

  // Re-read locale so nav labels update on language switch
  const navItems = $derived([
    { id: 'tasks',     label: t('nav.tasks') },
    { id: 'gateway',   label: t('nav.gateway') },
    { id: 'telemetry', label: t('nav.telemetry') },
    { id: 'dspy',      label: t('nav.dspy') },
  ])

  const drawerBtns = $derived([
    { open: () => ui.runOpen    = true, icon: PlayIcon,        label: t('nav.run') },
    { open: () => ui.cfOpen     = true, icon: CloudUploadIcon, label: t('nav.cf') },
    { open: () => ui.marketOpen = true, icon: BookOpenIcon,    label: t('nav.skills') },
  ])
  void i18n.locale

  onMount(() => {
    router.init()
    const unreg = registerShortcuts({
      '1-false-false-false': () => router.navigate('tasks'),
      '2-false-false-false': () => router.navigate('gateway'),
      '3-false-false-false': () => router.navigate('telemetry'),
      '4-false-false-false': () => router.navigate('dspy'),
      'r-true-true-false': global(() => { ui.runOpen = true }),
      'Escape-false-false-false': () => {
        if (ui.activeModal) { ui.activeModal = null; return }
        ui.closeAll()
      },
      '/-false-false-false': () => {
        const el = document.querySelector<HTMLInputElement>('.sidebar-search input')
        el?.focus()
      },
    })

    tasksStore.refresh()
    tasksStore.startStream()

    return () => {
      tasksStore.stopStream()
      unreg()
    }
  })

  // Marketplace drawer tab: skills | plugins
  let marketTab = $state('skills')
</script>

<div class="app">
  <AppHeader
    taskCount={tasksStore.status?.tasks_count ?? tasksStore.tasks.length}
    totalCost={tasksStore.summary?.total_cost_usd ?? 0}
  />

  <nav class="nav">
    <div class="nav-left">
      {#each navItems as item}
        <button
          class="nav-btn"
          class:active={router.page === item.id}
          onclick={() => router.navigate(item.id)}
        >
          {item.label}
          {#if item.id === 'tasks' && tasksStore.unseenCount > 0}
            <span class="nav-badge">{tasksStore.unseenCount}</span>
          {/if}
        </button>
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

  {#if tasksStore.error && router.page === 'tasks'}
    <div class="error-banner">
      {t('app.apiError', { error: tasksStore.error })}
      <button onclick={() => { tasksStore.refresh(); toast.info(t('app.refreshing')) }}>{t('common.retry')}</button>
    </div>
  {/if}

  <div class="body">
    {#if router.page === 'tasks'}
      {#if tasksStore.loading && tasksStore.tasks.length === 0}
        <div class="loading"><Spinner size={24} /> {t('app.loadingTasks')}</div>
      {:else}
        <TaskSidebar />
        <main class="main">
          <PipelineInspector />
        </main>
        <CostPanel />
      {/if}

    {:else if router.page === 'gateway'}
      <GatewayPage />

    {:else if router.page === 'telemetry'}
      <TelemetryPage />

    {:else if router.page === 'dspy'}
      <DSPyPage />
    {/if}
  </div>
</div>

<!-- Drawers -->
<Drawer bind:open={ui.runOpen} title={t('app.runDrawerTitle')} width="480px">
  <RunPanel onTaskComplete={() => { ui.runOpen = false; tasksStore.refresh() }} />
</Drawer>

<Drawer bind:open={ui.cfOpen} title={t('app.cfDrawerTitle')} width="520px">
  <CFPage />
</Drawer>

<Drawer bind:open={ui.marketOpen} title={t('app.marketDrawerTitle')} width="min(920px, 96vw)">
  <div class="mkt-tabs">
    <button class="mkt-tab" class:active={marketTab === 'skills'} onclick={() => marketTab = 'skills'}>{t('mkt.skills')}</button>
    <button class="mkt-tab" class:active={marketTab === 'plugins'} onclick={() => marketTab = 'plugins'}>{t('mkt.plugins')}</button>
  </div>
  {#if marketTab === 'skills'}
    <MarketplacePage />
  {:else}
    <PluginsPage />
  {/if}
</Drawer>

<!-- Toast notifications -->
<Toast />

<style>
  .mkt-tabs { display: flex; gap: 4px; margin-bottom: 16px; border-bottom: 2px solid var(--border-default); }
  .mkt-tab {
    background: none; border: none; cursor: pointer;
    padding: 8px 14px; font-size: 13px; color: var(--text-muted);
    border-bottom: 2px solid transparent; margin-bottom: -1px;
  }
  .mkt-tab:hover { color: var(--text-primary); }
  .mkt-tab.active { color: var(--voly-orange); border-bottom-color: var(--voly-orange); }

  .app {
    height: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    border: 3px solid var(--voly-ink);
    background: var(--bg-primary);
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
    background-color: var(--bg-primary);
    background-image: conic-gradient(from 90deg at 2px 2px, color-mix(in srgb, var(--voly-orange) 8%, transparent) 25%, transparent 0);
    background-size: 18px 18px;
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
    border-bottom: 2px solid var(--voly-ink);
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
    border-radius: 0;
    color: var(--text-muted);
    background: transparent;
    transition: background 0.12s, color 0.12s;
  }

  .nav-btn:hover {
    background: var(--bg-inset);
    color: var(--text-primary);
  }

  .nav-btn.active {
    background: var(--voly-orange);
    color: #fffaf1;
    box-shadow: 3px 3px 0 color-mix(in srgb, var(--voly-ink) 65%, transparent);
  }

  .nav-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 16px;
    height: 14px;
    padding: 0 4px;
    border-radius: 0;
    background: var(--voly-ink);
    color: var(--accent-blue-foreground, #fff);
    font-size: 9px;
    font-weight: 700;
    margin-left: 4px;
    line-height: 1;
  }

  .drawer-trigger {
    height: 26px;
    padding: 0 9px;
    font-size: 11px;
    font-weight: 500;
    border-radius: 0;
    color: var(--text-muted);
    background: transparent;
    display: flex;
    align-items: center;
    gap: 5px;
    border: 2px solid var(--border-muted);
    transition: background 0.12s, color 0.12s, border-color 0.12s;
  }

  .drawer-trigger:hover {
    background: var(--bg-inset);
    color: var(--text-primary);
    border-color: var(--border-default);
  }
</style>
