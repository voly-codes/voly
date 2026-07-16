<script>
  import { onMount } from 'svelte'
  import { PlayIcon, StopCircleIcon, ZapIcon } from '../../icons.js'
  import { runTask, fetchAgents, fetchModels, fetchStatus, fetchEnvironment } from '../../api/client.js'
  import { ui } from '../../stores/uiStore.svelte'
  import RunParams from './RunParams.svelte'
  import RunResult from './RunResult.svelte'
  import EnvironmentBanner from './EnvironmentBanner.svelte'

  let { onTaskComplete } = $props()

  let task = $state('')
  let executor = $state('pipeline')
  let agent = $state('')
  let model = $state('')
  let cwd = $state('')

  let running = $state(false)
  let result = $state(null)
  let error = $state(null)
  let warning = $state(null)
  let startedAt = $state(null)

  const HYBRID_WARNING_LABELS = {
    hybrid_skipped_no_cwd: 'Hybrid code generation skipped (no cwd set) — running chat-only.',
  }

  let agents = $state([])
  let models = $state([])
  let envReport = $state(null)
  let envLoading = $state(false)
  let executorAvailability = $state({})

  const executors = [
    { id: 'pipeline',            label: 'Pipeline (AI Gateway)' },
    { id: 'claude-code',         label: 'Claude Code' },
    { id: 'wrangler',            label: 'CF Workers AI (wrangler)' },
    { id: 'cf-containers',       label: 'CF Containers (sandbox)' },
    { id: 'zen',                 label: 'OpenCode Zen (free)' },
    { id: 'cursor',              label: 'Cursor Agent' },
    { id: 'opencode',            label: 'OpenCode Go' },
    { id: 'deepseek',            label: 'DeepSeek (text only)' },
    { id: 'workers-ai',          label: 'CF Workers AI (text only)' },
    { id: 'cloudflare-dynamic',  label: 'CF Dynamic Routing' },
  ]

  async function loadEnvironment() {
    envLoading = true
    try {
      const report = await fetchEnvironment(cwd)
      envReport = report
      executorAvailability = report?.executors ?? {}
      if (!cwd && report?.default_cwd) cwd = report.default_cwd
    } catch {
      envReport = null
    } finally {
      envLoading = false
    }
  }

  onMount(async () => {
    try { agents = await fetchAgents() } catch {}
    await loadModels()
    // Pre-fill cwd from server config (VOLY_PROJECT_CWD / default_cwd in voly.yaml)
    if (!cwd) {
      try {
        const st = await fetchStatus()
        if (st?.default_cwd) cwd = st.default_cwd
      } catch {}
    }
    await loadEnvironment()
  })

  // Re-check cwd when the user changes Working dir (debounced via idle effect)
  let cwdCheckTimer
  $effect(() => {
    const path = cwd
    if (cwdCheckTimer) clearTimeout(cwdCheckTimer)
    cwdCheckTimer = setTimeout(() => {
      if (envReport) loadEnvironment()
    }, 400)
    return () => clearTimeout(cwdCheckTimer)
  })

  async function loadModels() {
    try {
      models = await fetchModels(executor)
      if (model && !models.includes(model)) model = ''
    } catch {}
  }

  $effect(() => {
    executor
    loadModels()
  })

  async function submit() {
    if (!task.trim() || running) return
    running = true
    result = null
    error = null
    warning = null
    startedAt = Date.now()

    const runId = crypto.randomUUID()
    ui.pushRun({ id: runId, task: task.slice(0, 80), executor, agent: agent || 'auto', model: model || '—', startedAt: Date.now() })

    try {
      for await (const event of runTask({ task, executor, agent, model, cwd, max_turns: 30 })) {
        if (event.type === 'start') {
          if (event.hybrid_warning) {
            warning = HYBRID_WARNING_LABELS[event.hybrid_warning] ?? event.hybrid_warning
          }
        } else if (event.type === 'done') {
          result = event
          onTaskComplete?.()
        } else if (event.type === 'error') {
          error = event.error
        }
      }
    } catch (e) {
      error = e.message
    } finally {
      running = false
      ui.resolveRun(runId)
    }
  }

  function keydown(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') submit()
  }

  function elapsed() {
    if (!startedAt) return ''
    return ((Date.now() - startedAt) / 1000).toFixed(1) + 's'
  }

  let elapsedDisplay = $state('')
  $effect(() => {
    if (!running) { elapsedDisplay = ''; return }
    const iv = setInterval(() => { elapsedDisplay = elapsed() }, 200)
    return () => clearInterval(iv)
  })
</script>

<div class="run-panel">
  <EnvironmentBanner report={envReport} loading={envLoading} onRefresh={loadEnvironment} />
  <RunParams
    bind:executor
    bind:agent
    bind:model
    bind:cwd
    {executors}
    {agents}
    {models}
    {running}
    {executorAvailability}
  />

  <div class="results-area">
    {#if running}
      <div class="run-status running-pulse">
        <ZapIcon size="13" strokeWidth="2" />
        Running via <strong>{executor}</strong>… {elapsedDisplay}
      </div>
    {/if}

    {#if warning}
      <div class="run-warning">
        <strong>Warning:</strong> {warning}
      </div>
    {/if}

    {#if error}
      <div class="run-error">
        <strong>Error:</strong> {error}
      </div>
    {/if}

    {#if result && !error}
      <RunResult {result} />
    {/if}
  </div>

  <div class="input-area">
    <textarea
      class="task-input"
      placeholder="Describe your task…"
      bind:value={task}
      onkeydown={keydown}
      rows="2"
      disabled={running}
    ></textarea>
    <button
      class="run-btn"
      class:running
      onclick={submit}
      disabled={!task.trim() || running}
    >
      {#if running}
        <StopCircleIcon size="16" strokeWidth="2" />
      {:else}
        <PlayIcon size="16" strokeWidth="2" />
      {/if}
    </button>
  </div>
  <div class="input-hint">Ctrl+Enter to run</div>
</div>

<style>
  .run-panel {
    display: flex;
    flex-direction: column;
    height: 100%;
    background: var(--bg-surface);
  }

  .results-area {
    flex: 1;
    overflow-y: auto;
    padding: 8px 14px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .run-status {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: var(--running-fg);
    padding: 6px 10px;
    background: var(--running-bg);
    border: 1px solid var(--running-ring);
    border-radius: var(--radius-sm);
  }

  @keyframes pulse { 0%,100%{opacity:1}50%{opacity:0.6} }
  .running-pulse { animation: pulse 1.6s ease-in-out infinite; }

  .run-error {
    font-size: 12px;
    color: var(--accent-red);
    padding: 8px 10px;
    background: color-mix(in srgb, var(--accent-red) 10%, transparent);
    border: 1px solid color-mix(in srgb, var(--accent-red) 25%, transparent);
    border-radius: var(--radius-sm);
  }

  .run-warning {
    font-size: 12px;
    color: var(--accent-amber);
    padding: 8px 10px;
    background: color-mix(in srgb, var(--accent-amber) 10%, transparent);
    border: 1px solid color-mix(in srgb, var(--accent-amber) 25%, transparent);
    border-radius: var(--radius-sm);
  }

  .input-area {
    flex-shrink: 0;
    display: flex;
    align-items: flex-end;
    gap: 8px;
    padding: 8px 14px;
    border-top: 1px solid var(--border-default);
    background: var(--bg-surface);
  }

  .task-input {
    flex: 1;
    resize: none;
    background: var(--bg-inset);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    padding: 8px 10px;
    font-size: 13px;
    font-family: var(--font-sans);
    color: var(--text-primary);
    outline: none;
    transition: border-color 0.15s;
    line-height: 1.45;
  }
  .task-input:focus { border-color: var(--accent-blue); }
  .task-input::placeholder { color: var(--text-muted); }
  .task-input:disabled { opacity: 0.5; }

  .run-btn {
    flex-shrink: 0;
    width: 36px;
    height: 36px;
    border-radius: var(--radius-md);
    background: var(--accent-blue);
    color: var(--accent-blue-foreground);
    display: flex;
    align-items: center;
    justify-content: center;
    transition: opacity 0.15s, background 0.15s, transform 0.1s;
  }
  .run-btn:hover:not(:disabled) { opacity: 0.9; transform: scale(1.04); }
  .run-btn:disabled { opacity: 0.4; cursor: not-allowed; }
  .run-btn.running { background: var(--accent-rose); }

  .input-hint {
    flex-shrink: 0;
    font-size: 9px;
    color: var(--text-muted);
    text-align: center;
    padding: 0 14px 8px;
    opacity: 0.7;
  }
</style>
