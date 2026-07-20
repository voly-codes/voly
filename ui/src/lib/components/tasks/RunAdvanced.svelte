<script>
  const STORAGE_KEY = 'voly_run_advanced_open'

  let {
    a2a_mode = $bindable(''),
    timeout_s = $bindable(120),
    correlation_id = $bindable(''),
    running = false,
  } = $props()

  let open = $state(
    typeof localStorage !== 'undefined' && localStorage.getItem(STORAGE_KEY) === '1',
  )

  $effect(() => {
    localStorage?.setItem(STORAGE_KEY, open ? '1' : '0')
  })
</script>

<div class="run-advanced">
  <button type="button" class="toggle" onclick={() => (open = !open)} disabled={running}>
    Advanced {open ? '▾' : '▸'}
  </button>

  {#if open}
    <div class="advanced-grid">
      <div class="field">
        <label class="field-label" for="run-adv-a2a">A2A mode</label>
        <input
          id="run-adv-a2a"
          type="text"
          placeholder="auto"
          bind:value={a2a_mode}
          disabled={running}
        />
      </div>

      <div class="field">
        <label class="field-label" for="run-adv-timeout">Timeout (s)</label>
        <input
          id="run-adv-timeout"
          type="number"
          min="60"
          max="600"
          bind:value={timeout_s}
          disabled={running}
        />
      </div>

      <div class="field field-span2">
        <label class="field-label" for="run-adv-corr">Correlation ID</label>
        <input
          id="run-adv-corr"
          type="text"
          placeholder="leave blank = auto"
          bind:value={correlation_id}
          disabled={running}
        />
      </div>
    </div>
  {/if}
</div>

<style>
  .run-advanced {
    padding: 0 14px 6px;
    background: color-mix(in srgb, var(--bg-inset) 25%, transparent);
  }

  .toggle {
    font-size: 10px;
    color: var(--text-muted);
    padding: 4px 0;
    text-align: left;
    width: 100%;
  }
  .toggle:hover:not(:disabled) { color: var(--text-secondary); }
  .toggle:disabled { opacity: 0.5; cursor: not-allowed; }

  .advanced-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px 10px;
    padding-bottom: 6px;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 3px;
    min-width: 0;
  }

  .field-span2 { grid-column: span 2; }

  .field-label {
    font-size: 9px;
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .field input {
    width: 100%;
    height: 26px;
    padding: 0 8px;
    background: var(--bg-surface);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    font-size: 11px;
    color: var(--text-primary);
    outline: none;
  }

  .field input:focus { border-color: var(--accent-blue); }
  .field input:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
