<script>
  import { CodeIcon, CpuIcon, DatabaseIcon, GlobeIcon, LayersIcon, SquareTerminalIcon } from '../../icons.js'
  import { fetchTechCategories } from '../../api/client.js'

  let {
    open = $bindable(false),
    onPick = undefined,
    onSkip = undefined,
  } = $props()

  let categories = $state([])
  let selected = $state(null)
  let loading = $state(false)

  const ICONS = {
    web:     GlobeIcon,
    backend: CpuIcon,
    game:    CodeIcon,
    cli:     SquareTerminalIcon,
    data:    DatabaseIcon,
  }

  $effect(() => {
    if (open && categories.length === 0 && !loading) {
      loading = true
      fetchTechCategories()
        .then(r => { categories = r.categories ?? [] })
        .catch(() => {})
        .finally(() => { loading = false })
    }
    if (!open) selected = null
  })

  function pick() {
    if (!selected) return
    const cat = categories.find(c => c.id === selected)
    open = false
    onPick?.(cat?.entries ?? [])
  }

  function skip() {
    open = false
    onSkip?.()
  }

  function onKey(e) {
    if (e.key === 'Escape') skip()
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) pick()
  }
</script>

<svelte:window onkeydown={onKey} />

{#if open}
  <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
  <div class="modal-overlay" onclick={skip} role="dialog" aria-modal="true" aria-labelledby="cat-title">
    <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
    <div class="modal-panel" onclick={(e) => e.stopPropagation()}>
      <div class="modal-header">
        <LayersIcon size="14" strokeWidth="2" />
        <span id="cat-title" class="modal-title">What are you building?</span>
      </div>

      <div class="modal-body">
        <p class="hint">
          Tech stack wasn't detected automatically. Pick a category to choose versions,
          or skip to let the agent decide.
        </p>

        {#if loading}
          <div class="loading">Loading…</div>
        {:else}
          <div class="category-grid">
            {#each categories as cat}
              {@const Icon = ICONS[cat.id]}
              <button
                class="cat-card"
                class:active={selected === cat.id}
                onclick={() => selected = cat.id}
                type="button"
              >
                <div class="cat-icon">
                  {#if Icon}<Icon size="20" strokeWidth="1.5" />{/if}
                </div>
                <span class="cat-label">{cat.label}</span>
                <span class="cat-desc">{cat.description}</span>
              </button>
            {/each}
          </div>
        {/if}
      </div>

      <div class="modal-footer">
        <button class="btn ghost" onclick={skip}>Skip</button>
        <button class="btn primary" onclick={pick} disabled={!selected}>
          Choose versions →
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

  .loading {
    font-size: 12px;
    color: var(--text-muted);
    text-align: center;
    padding: 20px 0;
  }

  .category-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }

  .cat-card {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 12px;
    border: 1px solid var(--border-muted);
    border-radius: 8px;
    background: var(--bg-inset);
    cursor: pointer;
    text-align: left;
    transition: border-color 0.12s, background 0.12s;
  }

  .cat-card:hover {
    border-color: var(--border-default);
    background: var(--bg-surface);
  }

  .cat-card.active {
    border-color: var(--accent-blue, #3b82f6);
    background: color-mix(in srgb, var(--accent-blue, #3b82f6) 8%, var(--bg-inset));
  }

  .cat-icon {
    color: var(--text-muted);
    margin-bottom: 4px;
  }

  .cat-card.active .cat-icon {
    color: var(--accent-blue, #3b82f6);
  }

  .cat-label {
    font-size: 13px;
    font-weight: 600;
    color: var(--text-primary);
    line-height: 1.2;
  }

  .cat-desc {
    font-size: 11px;
    color: var(--text-muted);
    line-height: 1.35;
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

  .btn.primary:hover:not(:disabled) { filter: brightness(1.1); }
  .btn.primary:disabled { opacity: 0.4; cursor: not-allowed; }

  @keyframes fade-in { from { opacity: 0; } to { opacity: 1; } }
  @keyframes scale-in { from { transform: scale(0.96); opacity: 0; } to { transform: scale(1); opacity: 1; } }
</style>
