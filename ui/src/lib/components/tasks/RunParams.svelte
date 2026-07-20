<script>
  import {
    ChevronDownIcon, SquareTerminalIcon, FolderIcon,
  } from '../../icons.js'
  import CapabilityPreview from './CapabilityPreview.svelte'

  const API_BASE = import.meta.env.VITE_VOLY_API_BASE_URL ?? ''

  let {
    task = '',
    executor = $bindable('pipeline'),
    cwd = $bindable(''),
    executors = [],
    running = false,
    executorAvailability = {},
  } = $props()

  let browseOpen = $state(false)
  let browseEntries = $state([])
  let browseLoading = $state(false)

  function execBadge(id) {
    if (id === 'pipeline') return null
    const info = executorAvailability?.[id]
    if (!info) return null
    return info.available ? 'ok' : 'missing'
  }

  const executorHints = {
    pipeline:           'AI Gateway — cache, DLP, spend control (text only)',
    'claude-code':      'Claude Code CLI — reads/writes files · billing fallback → wrangler → zen',
    wrangler:           'CF Workers AI via wrangler dev — writes files via LocalPatchApplier',
    'cf-containers':    'Cloudflare Containers via sandbox-spike — needs VOLY_CF_CONTAINERS_URL + JWT',
    zen:                'OpenCode Zen — free tier, file-capable via opencode CLI',
    cursor:             'Cursor Agent IDE — reads/writes files directly',
    opencode:           'OpenCode Go CLI/API — file-capable agent',
    deepseek:           'DeepSeek API — text/code generation only',
    'workers-ai':       'CF Workers AI REST — text only, no file writes',
    'cloudflare-dynamic': 'CF AI Gateway dynamic routing — text only',
  }

  async function toggleBrowse() {
    if (running) return
    if (browseOpen) {
      browseOpen = false
      return
    }
    browseLoading = true
    browseEntries = []
    try {
      const q = cwd ? `?path=${encodeURIComponent(cwd)}` : ''
      const res = await fetch(`${API_BASE}/api/browse${q}`)
      const data = await res.json()
      if (data.error || !data.entries?.length) {
        browseOpen = false
        return
      }
      browseEntries = data.entries
      browseOpen = true
    } catch {
      browseOpen = false
    } finally {
      browseLoading = false
    }
  }

  /** @param {{ path: string }} entry */
  function selectDir(entry) {
    cwd = entry.path
    browseOpen = false
  }
</script>

<div class="params-card">
  <div class="params-grid">

    <div class="param">
      <label class="param-label" for="run-executor">
        <SquareTerminalIcon size="12" strokeWidth="2" />
        Executor
      </label>
      <div class="select-wrap">
        <select id="run-executor" bind:value={executor} disabled={running}>
          {#each executors as ex}
            {@const badge = execBadge(ex.id)}
            <option value={ex.id}>
              {ex.label}{badge === 'missing' ? ' — not installed' : badge === 'ok' ? ' ✓' : ''}
            </option>
          {/each}
        </select>
        <ChevronDownIcon size="10" strokeWidth="2" class="select-arrow" />
      </div>
      <span class="param-hint">
        {executorHints[executor] ?? ''}
        {#if execBadge(executor) === 'missing'}
          <span class="exec-missing"> · CLI/key not detected — see Environment tips</span>
        {/if}
      </span>
      <CapabilityPreview {task} {executor} onUse={(id) => { executor = id }} />
    </div>

    <div class="param param-cwd">
      <label class="param-label" for="run-cwd">
        <FolderIcon size="12" strokeWidth="2" />
        Working dir
      </label>
      <div class="cwd-row">
        <input
          id="run-cwd"
          placeholder="/path/to/project"
          bind:value={cwd}
          disabled={running}
        />
        <button
          type="button"
          class="browse-btn"
          onclick={toggleBrowse}
          disabled={running || browseLoading}
          title="Browse directories"
        >
          {browseLoading ? '…' : 'Browse'}
        </button>
      </div>
      {#if browseOpen && browseEntries.length}
        <ul class="browse-menu">
          {#each browseEntries as entry}
            <li>
              <button type="button" class="browse-item" onclick={() => selectDir(entry)}>
                {entry.name}/
              </button>
            </li>
          {/each}
        </ul>
      {/if}
      <span class="param-hint">{cwd ? 'executor writes here' : 'leave empty for text-only'}</span>
    </div>
  </div>
</div>

<style>
  .params-card {
    flex-shrink: 0;
    padding: 12px 14px 10px;
    border-bottom: 1px solid var(--border-muted);
    background: color-mix(in srgb, var(--bg-inset) 50%, transparent);
  }

  .params-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px 12px;
  }

  .param {
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
  }

  .param-cwd { position: relative; }

  .param-label {
    font-size: 10px;
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    display: flex;
    align-items: center;
    gap: 5px;
  }

  .param-hint {
    font-size: 9px;
    color: var(--text-muted);
    line-height: 1.2;
    white-space: normal;
  }

  .exec-missing {
    color: var(--accent-amber, #c4922a);
  }

  .select-wrap {
    position: relative;
    display: flex;
    align-items: center;
  }

  :global(.select-arrow) {
    position: absolute;
    right: 6px;
    color: var(--text-muted);
    pointer-events: none;
  }

  .cwd-row {
    display: flex;
    gap: 6px;
    align-items: center;
  }

  .cwd-row input {
    flex: 1;
    min-width: 0;
  }

  .browse-btn {
    flex-shrink: 0;
    height: 28px;
    padding: 0 8px;
    font-size: 11px;
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    background: var(--bg-surface);
    color: var(--text-secondary);
  }
  .browse-btn:hover:not(:disabled) { border-color: var(--accent-blue); color: var(--text-primary); }
  .browse-btn:disabled { opacity: 0.5; cursor: not-allowed; }

  .browse-menu {
    list-style: none;
    position: absolute;
    z-index: 20;
    left: 0;
    right: 0;
    top: calc(100% - 14px);
    max-height: 180px;
    overflow-y: auto;
    margin: 0;
    padding: 4px 0;
    background: var(--bg-surface);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    box-shadow: 0 4px 12px color-mix(in srgb, var(--text-primary) 8%, transparent);
  }

  .browse-item {
    width: 100%;
    text-align: left;
    padding: 5px 10px;
    font-size: 11px;
    font-family: var(--font-mono);
    color: var(--text-primary);
  }
  .browse-item:hover { background: var(--bg-surface-hover); }

  .param select, .param input {
    width: 100%;
    height: 28px;
    padding: 0 22px 0 8px;
    background: var(--bg-surface);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    font-size: 12px;
    color: var(--text-primary);
    outline: none;
    transition: border-color 0.15s;
  }

  .param select {
    appearance: none;
    cursor: pointer;
  }

  .param input { padding-right: 8px; }

  .param select:focus, .param input:focus { border-color: var(--accent-blue); }
  .param select:disabled, .param input:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
