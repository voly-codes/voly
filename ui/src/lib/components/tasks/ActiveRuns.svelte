<script>
  import { onMount } from 'svelte'
  import { t } from '../../i18n/localeStore.svelte.ts'
  import { fetchRuns } from '../../api/client.js'
  import { tasksStore } from '../../stores/tasksStore.svelte'

  const POLL_MS = 4000

  let runs = $state([])
  let expanded = $state('')
  let hadActive = false

  async function poll() {
    try {
      const data = await fetchRuns(true)
      runs = data.runs ?? []
      // A run just finished → its TaskEvent file exists now; refresh the list.
      if (hadActive && runs.length === 0) tasksStore.refresh()
      hadActive = runs.length > 0
    } catch {
      runs = []
    }
  }

  onMount(() => {
    poll()
    const timer = setInterval(poll, POLL_MS)
    return () => clearInterval(timer)
  })

  function fmtElapsed(s) {
    if (s < 60) return `${Math.round(s)}s`
    return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`
  }

  const STEP_COLOR = {
    verified: 'var(--accent-green)',
    done: 'var(--accent-green)',
    running: 'var(--accent-amber)',
    verifying: 'var(--accent-amber)',
    failed: 'var(--accent-red)',
    blocked: 'var(--accent-red)',
  }
</script>

{#if runs.length}
  <div class="active-runs">
    <div class="ar-title">
      <span class="ar-pulse"></span>
      {t('runs.inProgress')} · {runs.length}
    </div>
    {#each runs as r (r.task_id)}
      <div class="ar-card" class:open={expanded === r.task_id}>
        <button
          class="ar-row"
          onclick={() => expanded = expanded === r.task_id ? '' : r.task_id}
        >
          <span class="ar-task" title={r.task}>{r.task}</span>
          <span class="ar-meta">
            {#if r.current_role}
              <span class="ar-role">{r.current_role}</span>
            {/if}
            {#if r.total_roles > 1}
              <span class="ar-progress">{r.done_roles}/{r.total_roles}</span>
            {/if}
            <span class="ar-elapsed">{fmtElapsed(r.elapsed_seconds)}</span>
          </span>
        </button>
        {#if expanded === r.task_id}
          <div class="ar-detail">
            <div class="ar-detail-line">
              <span class="ar-label">id</span>
              <code>{r.task_id.slice(0, 12)}</code>
              <span class="ar-label">{t('runs.heartbeat')}</span>
              <span class:stale={r.age_seconds > 60}>{Math.round(r.age_seconds)}s</span>
            </div>
            {#if r.roles?.length > 1}
              <div class="ar-roles">
                {#each r.roles as role, i}
                  <span
                    class="ar-role-chip"
                    class:done={i < r.done_roles}
                    class:current={role === r.current_role}
                  >{role}</span>
                {/each}
              </div>
            {/if}
            {#if r.step_statuses?.length}
              <div class="ar-steps">
                {#each r.step_statuses as s}
                  <span class="ar-step" style:color={STEP_COLOR[s.status] ?? 'var(--text-muted)'}>
                    {s.role ?? s.id}: {s.status}
                  </span>
                {/each}
              </div>
            {/if}
            {#if r.error}
              <div class="ar-error">{r.error}</div>
            {/if}
          </div>
        {/if}
      </div>
    {/each}
  </div>
{/if}

<style>
  .active-runs {
    padding: 8px 10px;
    border-bottom: 1px solid var(--border-default);
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .ar-title {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-muted);
  }

  .ar-pulse {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--accent-amber);
    animation: ar-blink 1.2s ease-in-out infinite;
  }
  @keyframes ar-blink {
    50% { opacity: 0.25; }
  }

  .ar-card {
    background: var(--bg-inset);
    border: 1px solid var(--border-muted);
    border-radius: var(--radius-sm);
  }
  .ar-card.open { border-color: var(--border-default); }

  .ar-row {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    padding: 6px 8px;
    background: none;
    border: none;
    cursor: pointer;
    text-align: left;
  }

  .ar-task {
    flex: 1;
    min-width: 0;
    font-size: 11px;
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .ar-meta {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-shrink: 0;
  }

  .ar-role {
    font-size: 9px;
    font-weight: 600;
    color: var(--accent-amber);
    font-family: var(--font-mono);
  }

  .ar-progress,
  .ar-elapsed {
    font-size: 10px;
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
  }

  .ar-detail {
    padding: 6px 8px 8px;
    border-top: 1px solid var(--border-muted);
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .ar-detail-line {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 10px;
    color: var(--text-secondary);
  }
  .ar-detail-line code { font-size: 10px; color: var(--text-muted); }
  .ar-label { color: var(--text-muted); }
  .stale { color: var(--accent-red); }

  .ar-roles,
  .ar-steps {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }

  .ar-role-chip {
    font-size: 9px;
    padding: 1px 6px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-muted);
    color: var(--text-muted);
  }
  .ar-role-chip.done {
    color: var(--accent-green);
    border-color: color-mix(in srgb, var(--accent-green) 30%, transparent);
  }
  .ar-role-chip.current {
    color: var(--accent-amber);
    border-color: color-mix(in srgb, var(--accent-amber) 40%, transparent);
    background: color-mix(in srgb, var(--accent-amber) 10%, transparent);
  }

  .ar-step {
    font-size: 9.5px;
    font-family: var(--font-mono);
  }

  .ar-error {
    font-size: 10px;
    color: var(--accent-red);
    word-break: break-word;
  }
</style>
