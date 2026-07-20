<script>
  import {
    ChevronDownIcon, UsersRoundIcon, BrainCircuitIcon,
  } from '../../icons.js'

  const STORAGE_KEY = 'voly_run_options_open'

  let {
    agent = $bindable(''),
    model = $bindable(''),
    max_turns = $bindable(40),
    dry_run = $bindable(false),
    repo_url = $bindable(''),
    agents = [],
    models = [],
    running = false,
  } = $props()

  let open = $state(
    typeof localStorage !== 'undefined' && localStorage.getItem(STORAGE_KEY) === '1',
  )

  $effect(() => {
    localStorage?.setItem(STORAGE_KEY, open ? '1' : '0')
  })
</script>

<div class="run-options">
  <button type="button" class="toggle" onclick={() => (open = !open)} disabled={running}>
    Options {open ? '▾' : '▸'}
  </button>

  {#if open}
    <div class="options-grid">
      <div class="field">
        <label class="field-label" for="run-opt-agent">
          <UsersRoundIcon size="11" strokeWidth="2" />
          Agent
        </label>
        <div class="select-wrap">
          <select id="run-opt-agent" bind:value={agent} disabled={running}>
            <option value="">auto</option>
            {#each agents as a}
              <option value={a}>{a}</option>
            {/each}
          </select>
          <ChevronDownIcon size="10" strokeWidth="2" class="select-arrow" />
        </div>
      </div>

      <div class="field">
        <label class="field-label" for="run-opt-model">
          <BrainCircuitIcon size="11" strokeWidth="2" />
          Model
        </label>
        <div class="select-wrap">
          <select id="run-opt-model" bind:value={model} disabled={running}>
            <option value="">auto</option>
            {#each models as m}
              <option value={m}>{m}</option>
            {/each}
          </select>
          <ChevronDownIcon size="10" strokeWidth="2" class="select-arrow" />
        </div>
      </div>

      <div class="field">
        <label class="field-label" for="run-opt-turns">Max turns</label>
        <input
          id="run-opt-turns"
          type="number"
          min="1"
          max="100"
          bind:value={max_turns}
          disabled={running}
        />
      </div>

      <div class="field field-check">
        <label class="check-label">
          <input type="checkbox" bind:checked={dry_run} disabled={running} />
          Dry run
        </label>
      </div>

      <div class="field field-span2">
        <label class="field-label" for="run-opt-repo">Repo URL</label>
        <input
          id="run-opt-repo"
          type="text"
          placeholder="github.com/owner/repo"
          bind:value={repo_url}
          disabled={running}
        />
      </div>
    </div>
  {/if}
</div>

<style>
  .run-options {
    padding: 0 14px 6px;
    border-top: 1px solid var(--border-muted);
    background: color-mix(in srgb, var(--bg-inset) 40%, transparent);
  }

  .toggle {
    font-size: 11px;
    font-weight: 600;
    color: var(--text-secondary);
    padding: 6px 0;
    text-align: left;
    width: 100%;
  }
  .toggle:hover:not(:disabled) { color: var(--text-primary); }
  .toggle:disabled { opacity: 0.5; cursor: not-allowed; }

  .options-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px 10px;
    padding-bottom: 8px;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
  }

  .field-span2 { grid-column: span 2; }

  .field-check {
    justify-content: flex-end;
    padding-bottom: 2px;
  }

  .field-label {
    font-size: 10px;
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .check-label {
    font-size: 12px;
    color: var(--text-secondary);
    display: flex;
    align-items: center;
    gap: 6px;
    cursor: pointer;
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

  .field select,
  .field input[type='text'],
  .field input[type='number'] {
    width: 100%;
    height: 28px;
    padding: 0 22px 0 8px;
    background: var(--bg-surface);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    font-size: 12px;
    color: var(--text-primary);
    outline: none;
  }

  .field input[type='number'] { padding-right: 8px; }

  .field select {
    appearance: none;
    cursor: pointer;
  }

  .field select:focus,
  .field input:focus { border-color: var(--accent-blue); }

  .field select:disabled,
  .field input:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
