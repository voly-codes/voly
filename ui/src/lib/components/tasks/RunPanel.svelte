<script>
  import { onMount } from 'svelte'
  import { PlayIcon, StopCircleIcon, ZapIcon } from '../../icons.js'
  import { runTask, fetchAgents, fetchModels, fetchStatus, fetchEnvironment, suggestSkills, detectTech } from '../../api/client.js'
  import CategoryPickerModal from './CategoryPickerModal.svelte'
  import { ui } from '../../stores/uiStore.svelte'
  import RunParams from './RunParams.svelte'
  import RunOptions from './RunOptions.svelte'
  import RunAdvanced from './RunAdvanced.svelte'
  import DiffPreview from './DiffPreview.svelte'
  import RunResult from './RunResult.svelte'
  import EnvironmentBanner from './EnvironmentBanner.svelte'
  import SkillSuggestModal from './SkillSuggestModal.svelte'
  import TechSelectionModal from './TechSelectionModal.svelte'

  let { onTaskComplete } = $props()

  let task = $state('')
  let executor = $state('pipeline')
  let agent = $state('')
  let model = $state('')
  let cwd = $state('')
  let max_turns = $state(40)
  let dry_run = $state(false)
  let repo_url = $state('')
  let a2a_mode = $state('')
  let timeout_s = $state(120)
  let correlation_id = $state('')
  let workflow = $state('')
  let max_rounds = $state(3)
  let deadline_seconds = $state(900)

  let running = $state(false)
  let checkingSkills = $state(false)
  let result = $state(null)
  let error = $state(null)
  let warning = $state(null)
  let startedAt = $state(null)

  let skillGateOpen = $state(false)
  let skillSuggestions = $state([])
  let skillInstalling = $state(false)

  let techGateOpen = $state(false)
  let techDetected = $state([])
  let confirmedTechStack = $state([])
  let checkingTech = $state(false)

  let categoryPickerOpen = $state(false)

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

  /** Gate 1: suggest marketplace skills → Gate 2: tech detection → run. */
  async function submit() {
    if (!task.trim() || running || checkingSkills || skillGateOpen || checkingTech || techGateOpen) return
    if (workflow && !cwd.trim()) {
      error = 'Review workflow requires a working directory.'
      return
    }
    checkingSkills = true
    error = null
    try {
      const data = await suggestSkills(task.trim(), 5)
      const suggestions = data?.suggestions ?? []
      if (suggestions.length > 0) {
        skillSuggestions = suggestions
        skillGateOpen = true  // SkillSuggestModal calls checkTechGate on close
        return
      }
    } catch {
      // Marketplace down / suggest failed — do not block the run.
    } finally {
      checkingSkills = false
    }
    await checkTechGate()
  }

  /** Gate 2: detect tech stack — show TechSelectionModal if found, CategoryPickerModal if not. */
  async function checkTechGate() {
    if (executor === 'pipeline' || executor === 'claude-code' || executor === 'cursor') {
      checkingTech = true
      try {
        const data = await detectTech(task.trim(), cwd)
        const detected = data?.detected ?? []
        if (detected.length > 0) {
          techDetected = detected
          techGateOpen = true
          return
        }
        // Nothing detected — show category picker so user can choose a stack
        categoryPickerOpen = true
        return
      } catch {
        // Detection endpoint down — don't block the run.
      } finally {
        checkingTech = false
      }
    }
    await startRun([])
  }

  function onCategoryPick(entries) {
    techDetected = entries
    techGateOpen = true
  }

  function onTechConfirm(selected) {
    confirmedTechStack = selected
    startRun(selected)
  }

  function onTechSkip() {
    confirmedTechStack = []
    startRun([])
  }

  function buildRunRequest(techStack) {
    const req = {
      task: task.trim(),
      executor,
      agent,
      model,
      cwd,
      tech_stack: techStack,
    }
    if (max_turns !== 40) req.max_turns = max_turns
    if (dry_run) req.dry_run = dry_run
    if (repo_url.trim()) req.repo_url = repo_url.trim()
    if (a2a_mode.trim()) req.a2a_mode = a2a_mode.trim()
    if (timeout_s !== 120) req.timeout = timeout_s
    if (correlation_id.trim()) req.correlation_id = correlation_id.trim()
    if (workflow) {
      req.workflow = workflow
      req.max_rounds = Number(max_rounds)
      req.deadline_seconds = Number(deadline_seconds)
      delete req.dry_run
    }
    return req
  }

  async function startRun(techStack = []) {
    if (!task.trim() || running) return
    running = true
    result = null
    error = null
    warning = null
    startedAt = Date.now()

    const runId = crypto.randomUUID()
    ui.pushRun({ id: runId, task: task.slice(0, 80), executor, agent: agent || 'auto', model: model || '—', startedAt: Date.now() })

    try {
      for await (const event of runTask(buildRunRequest(techStack))) {
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

  const busy = $derived(running || checkingSkills || skillInstalling || checkingTech)
</script>

<div class="run-panel">
  <EnvironmentBanner report={envReport} loading={envLoading} onRefresh={loadEnvironment} />
  <RunParams
    bind:executor
    bind:cwd
    {task}
    {executors}
    running={busy}
    {executorAvailability}
  />

  <div class="results-area">
    {#if checkingSkills}
      <div class="run-status">
        <ZapIcon size="13" strokeWidth="2" />
        Looking for relevant marketplace skills…
      </div>
    {/if}

    {#if checkingTech}
      <div class="run-status">
        <ZapIcon size="13" strokeWidth="2" />
        Detecting tech stack…
      </div>
    {/if}

    {#if running}
      <div class="run-status running-pulse">
        <ZapIcon size="13" strokeWidth="2" />
        Running via <strong>{executor}</strong>… {elapsedDisplay}
        {#if confirmedTechStack.length}
          <span class="tech-chips">
            {#each confirmedTechStack as item}
              <span class="tech-chip">{item.label} {item.version}</span>
            {/each}
          </span>
        {/if}
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

  <div class="input-section">
    <div class="input-area">
      <textarea
        class="task-input"
        placeholder="Describe your task…"
        bind:value={task}
        onkeydown={keydown}
        rows="2"
        disabled={busy}
      ></textarea>
    </div>

    <RunOptions
      bind:agent
      bind:model
      bind:max_turns
      bind:dry_run
      bind:repo_url
      {agents}
      {models}
      running={busy}
    />

    <RunAdvanced
      bind:a2a_mode
      bind:timeout_s
      bind:correlation_id
      bind:workflow
      bind:max_rounds
      bind:deadline_seconds
      running={busy}
    />

    {#if result?.dry_run_diff}
      <DiffPreview diff={result.dry_run_diff} />
    {/if}

    <div class="run-row">
      <button
        class="run-btn"
        class:running={busy}
        onclick={submit}
        disabled={!task.trim() || busy}
      >
        {#if busy}
          <StopCircleIcon size="16" strokeWidth="2" />
        {:else}
          <PlayIcon size="16" strokeWidth="2" />
        {/if}
      </button>
      <div class="input-hint">Ctrl+Enter to run</div>
    </div>
  </div>
</div>

<SkillSuggestModal
  bind:open={skillGateOpen}
  bind:installing={skillInstalling}
  suggestions={skillSuggestions}
  onRun={checkTechGate}
  onSkip={checkTechGate}
/>

<TechSelectionModal
  bind:open={techGateOpen}
  detected={techDetected}
  onConfirm={onTechConfirm}
  onSkip={onTechSkip}
/>

<CategoryPickerModal
  bind:open={categoryPickerOpen}
  onPick={onCategoryPick}
  onSkip={() => startRun([])}
/>

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

  .tech-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-left: 4px;
  }

  .tech-chip {
    font-size: 10px;
    padding: 1px 6px;
    border-radius: 4px;
    background: color-mix(in srgb, var(--accent-blue) 15%, transparent);
    color: var(--accent-blue);
    border: 1px solid color-mix(in srgb, var(--accent-blue) 30%, transparent);
    font-family: var(--font-mono);
    white-space: nowrap;
  }

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

  .input-section {
    flex-shrink: 0;
    border-top: 1px solid var(--border-default);
    background: var(--bg-surface);
  }

  .input-area {
    display: flex;
    padding: 8px 14px 0;
  }

  .run-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 6px 14px 8px;
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
    font-size: 9px;
    color: var(--text-muted);
    opacity: 0.7;
  }
</style>
