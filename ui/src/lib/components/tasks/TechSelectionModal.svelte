<script>
  import { AlertCircleIcon, LayersIcon } from '../../icons.js'
  import { techPreflight } from '../../api/client.js'

  let {
    open = $bindable(false),
    detected = [],
    onConfirm = undefined,
    onSkip = undefined,
  } = $props()

  // Local editable copy — user can change version per entry
  let selections = $state([])
  // Preflight: name → true/false (only runtimes with system binaries)
  let availability = $state({})

  $effect(() => {
    if (open && detected.length) {
      selections = detected.map(e => ({ ...e }))
      availability = {}
      const names = detected.map(e => e.name)
      techPreflight(names)
        .then(r => { availability = r.available ?? {} })
        .catch(() => {})
    }
  })

  function setVersion(name, version) {
    selections = selections.map(e => e.name === name ? { ...e, version } : e)
  }

  function confirm() {
    open = false
    onConfirm?.(selections)
  }

  function skip() {
    open = false
    onSkip?.()
  }

  function onKey(e) {
    if (e.key === 'Escape') skip()
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) confirm()
  }

  const categoryOrder = ['frontend', 'backend', 'language', 'build', 'testing', 'database', 'infra']
  const categoryLabel = {
    frontend: 'Frontend', backend: 'Backend', language: 'Language',
    build: 'Build', testing: 'Testing', database: 'Database', infra: 'Infrastructure',
  }

  let grouped = $derived(
    categoryOrder
      .map(cat => ({ cat, items: selections.filter(e => e.category === cat) }))
      .filter(g => g.items.length > 0)
  )
</script>

<svelte:window onkeydown={onKey} />

{#if open}
  <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
  <div
    class="modal-overlay"
    onclick={skip}
    role="dialog"
    aria-modal="true"
    aria-labelledby="tech-gate-title"
  >
    <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
    <div class="modal-panel" onclick={(e) => e.stopPropagation()}>
      <div class="modal-header">
        <LayersIcon size="14" strokeWidth="2" />
        <span id="tech-gate-title" class="modal-title">Confirm tech stack</span>
      </div>

      <div class="modal-body">
        <p class="hint">
          Select the exact versions to use. Agents will be pinned to these —
          no guessing, no auto-upgrades.
        </p>

        {#each grouped as { cat, items }}
          <div class="group">
            <div class="group-label">{categoryLabel[cat] ?? cat}</div>
            {#each items as entry}
              <div class="tech-row" class:missing={availability[entry.name] === false}>
                <div class="tech-meta">
                  <div class="tech-name-row">
                    <span class="tech-name">{entry.label}</span>
                    {#if availability[entry.name] === false}
                      <span class="not-installed-badge" title="Runtime not found in PATH — install it or the agent will fail at the test/run step">
                        <AlertCircleIcon size="11" strokeWidth="2" />
                        not installed
                      </span>
                    {/if}
                  </div>
                  {#if entry.notes}
                    <span class="tech-notes">{entry.notes}</span>
                  {/if}
                </div>
                <select
                  class="version-select"
                  value={entry.version}
                  onchange={(e) => setVersion(entry.name, e.currentTarget.value)}
                  aria-label="Version for {entry.label}"
                >
                  {#each entry.versions as v}
                    <option value={v}>{v}{v === entry.versions[0] ? ' (latest)' : ''}</option>
                  {/each}
                </select>
              </div>
            {/each}
          </div>
        {/each}
      </div>

      <div class="modal-footer">
        <button class="btn ghost" onclick={skip}>Skip</button>
        <button class="btn primary" onclick={confirm}>
          Use this stack
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .modal-overlay {
    position: fixed;
    inset: 0;
    z-index: 1000;
    background: rgba(0, 0, 0, 0.45);
    display: flex;
    align-items: center;
    justify-content: center;
    animation: fade-in 0.15s ease;
  }

  .modal-panel {
    width: min(560px, calc(100vw - 32px));
    max-height: calc(100vh - 48px);
    overflow: auto;
    background: var(--bg-surface);
    border: 1px solid var(--border-default);
    border-radius: 10px;
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.25);
    animation: scale-in 0.15s ease;
  }

  .modal-header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 14px 16px 0;
    color: var(--text-primary);
  }

  .modal-title {
    font-size: 14px;
    font-weight: 600;
  }

  .modal-body {
    padding: 12px 16px 8px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .hint {
    margin: 0;
    font-size: 12px;
    line-height: 1.45;
    color: var(--text-muted);
  }

  .group {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .group-label {
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--text-muted);
    padding-bottom: 2px;
    border-bottom: 1px solid var(--border-muted);
  }

  .tech-row {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    padding: 8px 10px;
    border: 1px solid var(--border-muted);
    border-radius: 7px;
    background: var(--bg-inset);
  }

  .tech-row.missing {
    border-color: color-mix(in srgb, var(--accent-amber) 40%, transparent);
    background: color-mix(in srgb, var(--accent-amber) 5%, var(--bg-inset));
  }

  .tech-meta {
    display: flex;
    flex-direction: column;
    gap: 3px;
    min-width: 0;
    flex: 1;
  }

  .tech-name-row {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
  }

  .tech-name {
    font-size: 13px;
    font-weight: 600;
    color: var(--text-primary);
  }

  .not-installed-badge {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    font-size: 10px;
    font-family: var(--font-mono);
    color: var(--accent-amber);
    background: color-mix(in srgb, var(--accent-amber) 12%, transparent);
    border: 1px solid color-mix(in srgb, var(--accent-amber) 35%, transparent);
    border-radius: 4px;
    padding: 1px 5px;
    cursor: default;
  }

  .tech-notes {
    font-size: 11px;
    color: var(--text-muted);
    line-height: 1.35;
  }

  .version-select {
    flex-shrink: 0;
    font-size: 12px;
    padding: 4px 8px;
    border-radius: 6px;
    border: 1px solid var(--border-default);
    background: var(--bg-surface);
    color: var(--text-primary);
    cursor: pointer;
    min-width: 110px;
  }

  .version-select:focus {
    outline: 2px solid var(--accent-blue, #3b82f6);
    outline-offset: 1px;
  }

  .modal-footer {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 8px;
    padding: 10px 16px 14px;
    border-top: 1px solid var(--border-default);
  }

  .btn {
    font-size: 12px;
    padding: 7px 14px;
    border-radius: 6px;
    border: 1px solid var(--border-default);
    cursor: pointer;
    background: var(--bg-surface);
    color: var(--text-primary);
  }

  .btn.ghost {
    border-color: transparent;
    color: var(--text-muted);
  }

  .btn.primary {
    background: var(--accent-blue, #3b82f6);
    border-color: var(--accent-blue, #3b82f6);
    color: #fff;
  }

  .btn.primary:hover {
    filter: brightness(1.1);
  }

  @keyframes fade-in {
    from { opacity: 0; }
    to { opacity: 1; }
  }

  @keyframes scale-in {
    from { transform: scale(0.96); opacity: 0; }
    to { transform: scale(1); opacity: 1; }
  }
</style>
