<script>
  import {
    ChevronDownIcon, SquareTerminalIcon, UsersRoundIcon,
    BrainCircuitIcon, FolderIcon,
  } from '../../icons.js'

  let { executor = $bindable('pipeline'), agent = $bindable(''), model = $bindable(''), cwd = $bindable(''), executors = [], agents = [], models = [], running = false } = $props()
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
            <option value={ex.id}>{ex.label}</option>
          {/each}
        </select>
        <ChevronDownIcon size="10" strokeWidth="2" class="select-arrow" />
      </div>
      <span class="param-hint">
        {executor === 'pipeline' ? 'AI Gateway (cache + DLP)' : 'IDE tool (direct files)'}
      </span>
    </div>

    <div class="param">
      <label class="param-label" for="run-agent">
        <UsersRoundIcon size="12" strokeWidth="2" />
        Agent
      </label>
      <div class="select-wrap">
        <select id="run-agent" bind:value={agent} disabled={running}>
          <option value="">auto</option>
          {#each agents as a}
            <option value={a}>{a}</option>
          {/each}
        </select>
        <ChevronDownIcon size="10" strokeWidth="2" class="select-arrow" />
      </div>
      <span class="param-hint">{agent || 'auto — router picks'}</span>
    </div>

    <div class="param">
      <label class="param-label" for="run-model">
        <BrainCircuitIcon size="12" strokeWidth="2" />
        Model
      </label>
      <div class="select-wrap">
        <select id="run-model" bind:value={model} disabled={running}>
          <option value="">auto</option>
          {#each models as m}
            <option value={m}>{m}</option>
          {/each}
        </select>
        <ChevronDownIcon size="10" strokeWidth="2" class="select-arrow" />
      </div>
      <span class="param-hint">{model || 'auto — router picks'}</span>
    </div>

    {#if executor !== 'pipeline'}
      <div class="param">
        <label class="param-label" for="run-cwd">
          <FolderIcon size="12" strokeWidth="2" />
          Working dir
        </label>
        <input
          id="run-cwd"
          placeholder={typeof window !== 'undefined' ? '~' : '/'}
          bind:value={cwd}
          disabled={running}
        />
        <span class="param-hint">Absolute path for executor</span>
      </div>
    {:else}
      <div class="param disabled">
        <label class="param-label">
          <FolderIcon size="12" strokeWidth="2" />
          Working dir
        </label>
        <div class="param-disabled-text">handled by pipeline</div>
        <span class="param-hint">&nbsp;</span>
      </div>
    {/if}
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

  .param.disabled {
    opacity: 0.4;
  }

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
    line-height: 1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .param-disabled-text {
    height: 28px;
    display: flex;
    align-items: center;
    font-size: 11px;
    color: var(--text-muted);
    padding: 0 8px;
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

  .param input {
    padding-right: 8px;
  }

  .param select:focus, .param input:focus { border-color: var(--accent-blue); }
  .param select:disabled, .param input:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
