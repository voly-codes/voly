<script>
  import { BookOpenIcon } from '../../icons.js'
  import { installSkill } from '../../api/client.js'

  let { suggestions = [] } = $props()

  // skill_suggestions install state: { [skill_id]: 'idle' | 'installing' | 'done' | 'error' }
  let installState = $state({})

  async function handleInstall(skillId) {
    installState = { ...installState, [skillId]: 'installing' }
    try {
      await installSkill(skillId)
      installState = { ...installState, [skillId]: 'done' }
    } catch {
      installState = { ...installState, [skillId]: 'error' }
    }
  }
</script>

{#if suggestions?.length}
  <div class="skill-suggest-banner">
    <div class="suggest-header">
      <BookOpenIcon size="11" strokeWidth="2" />
      <span>Relevant skills found in marketplace — install to improve future runs</span>
    </div>
    <div class="suggest-list">
      {#each suggestions as s}
        <div class="suggest-row">
          <span class="suggest-name">{s.name}</span>
          {#if s.description}
            <span class="suggest-desc">{s.description.slice(0, 80)}{s.description.length > 80 ? '…' : ''}</span>
          {/if}
          {#if s.install_kind === 'git' && s.repository}
            <span class="suggest-kind">git</span>
          {/if}
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
  </div>
{/if}

<style>
  .skill-suggest-banner {
    border-bottom: 1px solid var(--border-muted);
    padding: 7px 10px;
    background: color-mix(in srgb, var(--accent-teal) 6%, transparent);
  }

  .suggest-header {
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 10px;
    font-weight: 600;
    color: var(--accent-teal);
    margin-bottom: 6px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .suggest-list {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .suggest-row {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
  }

  .suggest-name {
    font-size: 11px;
    font-weight: 600;
    color: var(--text-primary);
    font-family: var(--font-mono);
    min-width: 100px;
  }

  .suggest-desc {
    font-size: 10.5px;
    color: var(--text-muted);
    flex: 1;
  }

  .suggest-kind {
    font-size: 9px;
    padding: 1px 5px;
    border-radius: var(--radius-sm);
    border: 1px solid color-mix(in srgb, var(--accent-purple) 30%, transparent);
    color: var(--accent-purple);
    background: color-mix(in srgb, var(--accent-purple) 10%, transparent);
  }

  .suggest-btn {
    font-size: 10px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: var(--radius-sm);
    border: 1px solid color-mix(in srgb, var(--accent-teal) 40%, transparent);
    background: color-mix(in srgb, var(--accent-teal) 12%, transparent);
    color: var(--accent-teal);
    cursor: pointer;
    flex-shrink: 0;
    transition: opacity 0.15s;
  }
  .suggest-btn:hover:not(:disabled) { opacity: 0.8; }
  .suggest-btn:disabled { opacity: 0.5; cursor: default; }
  .suggest-btn.installed {
    color: var(--accent-green);
    border-color: color-mix(in srgb, var(--accent-green) 30%, transparent);
    background: color-mix(in srgb, var(--accent-green) 10%, transparent);
    cursor: default;
  }
  .suggest-btn.err {
    color: var(--accent-red);
    border-color: color-mix(in srgb, var(--accent-red) 30%, transparent);
    background: color-mix(in srgb, var(--accent-red) 10%, transparent);
  }
</style>
