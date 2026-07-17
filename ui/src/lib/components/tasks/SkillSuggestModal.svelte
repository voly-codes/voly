<script>
  import { BookOpenIcon } from '../../icons.js'
  import { installSkill } from '../../api/client.js'

  let {
    open = $bindable(false),
    suggestions = [],
    installing = $bindable(false),
    onRun = undefined,
    onSkip = undefined,
  } = $props()

  // per-skill: idle | installing | done | error
  let installState = $state({})

  let anyInstalling = $derived(Object.values(installState).some(s => s === 'installing'))
  let installedCount = $derived(Object.values(installState).filter(s => s === 'done').length)
  let pendingCount = $derived(
    suggestions.filter(s => installState[s.id] !== 'done' && installState[s.id] !== 'installing').length,
  )

  async function handleInstall(skillId) {
    installState = { ...installState, [skillId]: 'installing' }
    installing = true
    try {
      await installSkill(skillId)
      installState = { ...installState, [skillId]: 'done' }
    } catch {
      installState = { ...installState, [skillId]: 'error' }
    } finally {
      installing = Object.values(installState).some(s => s === 'installing')
    }
  }

  async function installAll() {
    for (const s of suggestions) {
      if (installState[s.id] === 'done') continue
      await handleInstall(s.id)
    }
  }

  function runNow() {
    open = false
    onRun?.()
  }

  function skip() {
    open = false
    onSkip?.()
  }

  function onKey(e) {
    if (e.key === 'Escape' && !anyInstalling) skip()
  }
</script>

<svelte:window onkeydown={onKey} />

{#if open}
  <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
  <div
    class="modal-overlay"
    onclick={() => { if (!anyInstalling) skip() }}
    role="dialog"
    aria-modal="true"
    aria-labelledby="skill-gate-title"
  >
    <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
    <div class="modal-panel" onclick={(e) => e.stopPropagation()}>
      <div class="modal-header">
        <BookOpenIcon size="14" strokeWidth="2" />
        <span id="skill-gate-title" class="modal-title">Relevant skills for this task</span>
      </div>

      <div class="modal-body">
        <p class="hint">
          Install recommended skills before the run — they will be injected into agent context.
          Wait until install finishes, then start the task.
        </p>

        <div class="suggest-list">
          {#each suggestions as s}
            <div class="suggest-row">
              <div class="suggest-meta">
                <span class="suggest-name">{s.name || s.id}</span>
                {#if s.description}
                  <span class="suggest-desc">{s.description.slice(0, 100)}{s.description.length > 100 ? '…' : ''}</span>
                {/if}
                {#if s.install_kind === 'git' && s.repository}
                  <span class="suggest-kind">git</span>
                {/if}
              </div>
              {#if installState[s.id] === 'done'}
                <span class="suggest-btn installed">installed</span>
              {:else if installState[s.id] === 'error'}
                <button class="suggest-btn err" onclick={() => handleInstall(s.id)}>retry</button>
              {:else}
                <button
                  class="suggest-btn"
                  disabled={installState[s.id] === 'installing'}
                  onclick={() => handleInstall(s.id)}
                >{installState[s.id] === 'installing' ? '…' : 'Install'}</button>
              {/if}
            </div>
          {/each}
        </div>

        {#if installedCount > 0}
          <p class="status-ok">{installedCount} installed — ready to run</p>
        {/if}
      </div>

      <div class="modal-footer">
        <button class="btn ghost" disabled={anyInstalling} onclick={skip}>Skip &amp; run</button>
        {#if pendingCount > 0}
          <button class="btn secondary" disabled={anyInstalling} onclick={installAll}>
            {anyInstalling ? 'Installing…' : 'Install all'}
          </button>
        {/if}
        <button class="btn primary" disabled={anyInstalling} onclick={runNow}>
          {installedCount > 0 ? 'Run with skills' : 'Run anyway'}
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
    width: min(520px, calc(100vw - 32px));
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
  }

  .hint {
    margin: 0 0 12px;
    font-size: 12px;
    line-height: 1.45;
    color: var(--text-muted);
  }

  .suggest-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .suggest-row {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    padding: 10px;
    border: 1px solid var(--border-muted);
    border-radius: 8px;
    background: var(--bg-inset);
  }

  .suggest-meta {
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
  }

  .suggest-name {
    font-size: 13px;
    font-weight: 600;
    color: var(--text-primary);
  }

  .suggest-desc {
    font-size: 11px;
    color: var(--text-muted);
    line-height: 1.4;
  }

  .suggest-kind {
    align-self: flex-start;
    font-size: 10px;
    padding: 1px 6px;
    border-radius: 4px;
    background: var(--bg-surface);
    color: var(--text-muted);
    border: 1px solid var(--border-muted);
  }

  .suggest-btn {
    flex-shrink: 0;
    font-size: 11px;
    padding: 5px 10px;
    border-radius: 6px;
    border: 1px solid var(--border-default);
    background: var(--bg-surface);
    color: var(--text-primary);
    cursor: pointer;
  }

  .suggest-btn:disabled {
    opacity: 0.6;
    cursor: wait;
  }

  .suggest-btn.installed {
    border-color: var(--accent-green, #3a9);
    color: var(--accent-green, #3a9);
    cursor: default;
  }

  .suggest-btn.err {
    border-color: var(--accent-red, #c55);
    color: var(--accent-red, #c55);
  }

  .status-ok {
    margin: 10px 0 0;
    font-size: 12px;
    color: var(--accent-green, #3a9);
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
    padding: 7px 12px;
    border-radius: 6px;
    border: 1px solid var(--border-default);
    cursor: pointer;
    background: var(--bg-surface);
    color: var(--text-primary);
  }

  .btn:disabled {
    opacity: 0.55;
    cursor: wait;
  }

  .btn.ghost {
    border-color: transparent;
    color: var(--text-muted);
  }

  .btn.secondary {
    background: var(--bg-inset);
  }

  .btn.primary {
    background: var(--accent-blue, #3b82f6);
    border-color: var(--accent-blue, #3b82f6);
    color: #fff;
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
