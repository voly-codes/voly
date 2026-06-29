<script>
  import { onMount } from 'svelte'
  import {
    PlayIcon, StopCircleIcon, ChevronDownIcon,
    ZapIcon, CpuIcon, ClockIcon,
  } from '../../icons.js'
  import { runTask, fetchAgents, fetchModels } from '../../api/client.js'

  let { onTaskComplete } = $props()

  let task = $state('')
  let executor = $state('pipeline')
  let agent = $state('')
  let model = $state('')
  let cwd = $state('')

  let running = $state(false)
  let result = $state(null)
  let error = $state(null)
  let startedAt = $state(null)

  let agents = $state([])
  let models = $state([])

  const executors = [
    { id: 'pipeline',    label: 'Pipeline (AI Gateway)' },
    { id: 'cursor',      label: 'Cursor Agent' },
    { id: 'claude-code', label: 'Claude Code' },
    { id: 'opencode',    label: 'OpenCode' },
    { id: 'deepseek',    label: 'DeepSeek' },
    { id: 'zen',         label: 'OpenCode Zen (readonly)' },
  ]

  onMount(async () => {
    try { agents = await fetchAgents() } catch {}
    await loadModels()
  })

  async function loadModels() {
    try {
      models = await fetchModels(executor)
      // reset model selection if current value not in new list
      if (model && !models.includes(model)) model = ''
    } catch {}
  }

  $effect(() => {
    executor  // re-run when executor changes
    loadModels()
  })

  async function submit() {
    if (!task.trim() || running) return
    running = true
    result = null
    error = null
    startedAt = Date.now()

    try {
      for await (const event of runTask({ task, executor, agent, model, cwd, max_turns: 30 })) {
        if (event.type === 'done') {
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
  <div class="run-form">
    <textarea
      class="task-input"
      placeholder="Describe your task… (Ctrl+Enter to run)"
      bind:value={task}
      onkeydown={keydown}
      rows="3"
      disabled={running}
    ></textarea>

    <div class="run-options">
      <div class="option-group">
        <label class="option-label" for="run-executor">Executor</label>
        <div class="select-wrap">
          <select id="run-executor" class="option-select" bind:value={executor} disabled={running}>
            {#each executors as ex}
              <option value={ex.id}>{ex.label}</option>
            {/each}
          </select>
          <ChevronDownIcon size="12" strokeWidth="2" class="select-arrow" />
        </div>
      </div>

      <div class="option-group">
        <label class="option-label" for="run-agent">Agent</label>
        <div class="select-wrap">
          <select id="run-agent" class="option-select" bind:value={agent} disabled={running}>
            <option value="">auto</option>
            {#each agents as a}
              <option value={a}>{a}</option>
            {/each}
          </select>
          <ChevronDownIcon size="12" strokeWidth="2" class="select-arrow" />
        </div>
      </div>

      <div class="option-group">
        <label class="option-label" for="run-model">Model</label>
        <div class="select-wrap">
          <select id="run-model" class="option-select" bind:value={model} disabled={running}>
            <option value="">auto</option>
            {#each models as m}
              <option value={m}>{m}</option>
            {/each}
          </select>
          <ChevronDownIcon size="12" strokeWidth="2" class="select-arrow" />
        </div>
      </div>

      {#if executor !== 'pipeline'}
        <div class="option-group">
          <label class="option-label" for="run-cwd">Working dir</label>
          <input
            id="run-cwd"
            class="option-input"
            placeholder={typeof window !== 'undefined' ? '~' : '/'}
            bind:value={cwd}
            disabled={running}
          />
        </div>
      {/if}

      <button
        class="run-btn"
        class:running
        onclick={submit}
        disabled={!task.trim() || running}
      >
        {#if running}
          <StopCircleIcon size="14" strokeWidth="2" />
          {elapsedDisplay}
        {:else}
          <PlayIcon size="14" strokeWidth="2" />
          Run
        {/if}
      </button>
    </div>
  </div>

  {#if running}
    <div class="run-status running-pulse">
      <ZapIcon size="13" strokeWidth="2" />
      Running via <strong>{executor}</strong>… {elapsedDisplay}
    </div>
  {/if}

  {#if error}
    <div class="run-error">
      <strong>Error:</strong> {error}
    </div>
  {/if}

  {#if result && !error}
    <div class="run-result">
      <div class="result-header">
        <div class="result-meta">
          {#if result.agent}
            <span class="meta-chip">{result.agent}</span>
          {/if}
          {#if result.model}
            <span class="meta-chip model">{result.model}</span>
          {/if}
          {#if result.executor}
            <span class="meta-chip">{result.executor}</span>
          {/if}
          <span class="meta-chip {result.success ? 'ok' : 'err'}">
            {result.success ? 'completed' : 'failed'}
          </span>
        </div>
        <div class="result-stats">
          {#if result.duration_ms}
            <span class="stat"><ClockIcon size="11" strokeWidth="2" />{(result.duration_ms/1000).toFixed(2)}s</span>
          {/if}
          {#if result.usage}
            <span class="stat"><CpuIcon size="11" strokeWidth="2" />{result.usage.input_tokens}+{result.usage.output_tokens}</span>
          {/if}
          {#if result.cost_usd}
            <span class="stat">${result.cost_usd.toFixed(4)}</span>
          {/if}
          {#if result.num_turns}
            <span class="stat">{result.num_turns} turns</span>
          {/if}
        </div>
      </div>

      {#if result.content}
        <pre class="result-content">{result.content}</pre>
      {/if}

      {#if result.error}
        <div class="result-err-msg">{result.error}</div>
      {/if}
    </div>
  {/if}
</div>

<style>
  .run-panel {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 12px 16px;
    border-bottom: 1px solid var(--border-default);
    background: var(--bg-surface);
    flex-shrink: 0;
  }

  .run-form { display: flex; flex-direction: column; gap: 8px; }

  .task-input {
    width: 100%;
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
  }
  .task-input:focus { border-color: var(--accent-blue); }
  .task-input::placeholder { color: var(--text-muted); }
  .task-input:disabled { opacity: 0.6; }

  .run-options {
    display: flex;
    align-items: flex-end;
    gap: 8px;
    flex-wrap: wrap;
  }

  .option-group {
    display: flex;
    flex-direction: column;
    gap: 3px;
    flex: 1;
    min-width: 100px;
  }

  .option-label {
    font-size: 10px;
    color: var(--text-muted);
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .select-wrap {
    position: relative;
    display: flex;
    align-items: center;
  }

  .option-select, .option-input {
    width: 100%;
    height: 28px;
    padding: 0 8px;
    background: var(--bg-inset);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    font-size: 12px;
    color: var(--text-primary);
    outline: none;
  }
  .option-select { padding-right: 24px; appearance: none; cursor: pointer; }
  :global(.select-arrow) { position: absolute; right: 6px; color: var(--text-muted); pointer-events: none; }

  .option-select:focus, .option-input:focus { border-color: var(--accent-blue); }
  .option-select:disabled, .option-input:disabled { opacity: 0.6; }

  .run-btn {
    height: 28px;
    padding: 0 14px;
    background: var(--accent-blue);
    color: var(--accent-blue-foreground);
    border-radius: var(--radius-sm);
    font-size: 12px;
    font-weight: 500;
    display: flex;
    align-items: center;
    gap: 5px;
    flex-shrink: 0;
    transition: opacity 0.15s;
    white-space: nowrap;
  }
  .run-btn:hover:not(:disabled) { opacity: 0.9; }
  .run-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .run-btn.running { background: var(--accent-rose); }

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

  .run-result {
    background: var(--bg-inset);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    overflow: hidden;
  }

  .result-header {
    padding: 8px 10px;
    border-bottom: 1px solid var(--border-muted);
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }

  .result-meta { display: flex; gap: 4px; flex-wrap: wrap; flex: 1; }

  .meta-chip {
    font-size: 10px;
    font-weight: 500;
    padding: 1px 6px;
    border-radius: var(--radius-sm);
    background: var(--bg-surface);
    border: 1px solid var(--border-default);
    color: var(--text-secondary);
  }
  .meta-chip.model { color: var(--accent-purple); border-color: color-mix(in srgb, var(--accent-purple) 30%, transparent); }
  .meta-chip.ok { color: var(--accent-green); border-color: color-mix(in srgb, var(--accent-green) 30%, transparent); }
  .meta-chip.err { color: var(--accent-red); border-color: color-mix(in srgb, var(--accent-red) 30%, transparent); }

  .result-stats {
    display: flex;
    gap: 8px;
    align-items: center;
    flex-shrink: 0;
  }

  .stat {
    display: flex;
    align-items: center;
    gap: 3px;
    font-size: 11px;
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
  }

  .result-content {
    padding: 12px;
    font-size: 12px;
    font-family: var(--font-mono);
    color: var(--text-primary);
    white-space: pre-wrap;
    word-break: break-word;
    max-height: 320px;
    overflow-y: auto;
    line-height: 1.6;
  }

  .result-err-msg {
    padding: 8px 12px;
    font-size: 12px;
    color: var(--accent-red);
  }
</style>
