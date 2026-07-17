<script>
  // Compact per-role status strip for multi-agent tasks (TaskHeader).
  // Highlights failed roles with their error so a `partial` status is
  // explainable at a glance without opening the inspector sections.
  let { assignments = [] } = $props()

  let failed = $derived(assignments.filter((a) => !a.ok && a.error))

  function dur(a) {
    const ms = a.duration_ms ?? 0
    if (!ms) return ''
    return ms >= 1000 ? `${Math.round(ms / 1000)}s` : `${Math.round(ms)}ms`
  }

  function shortErr(text) {
    const t = (text || '').replace(/\s+/g, ' ').trim()
    return t.length > 90 ? t.slice(0, 90) + '…' : t
  }
</script>

<div class="role-strip">
  {#each assignments as a}
    <span class="role-chip" class:role-failed={!a.ok} title={a.ok ? `${a.role} · ok` : `${a.role}: ${a.error || 'failed'}`}>
      <span class="role-dot" style="background:{a.ok ? 'var(--accent-green)' : 'var(--accent-red)'}"></span>
      {a.role}
      {#if dur(a)}<span class="role-dur">{dur(a)}</span>{/if}
    </span>
  {/each}
</div>

{#each failed as a}
  <div class="role-error" title={a.error}>
    <span class="role-error-name">{a.role}</span>
    {shortErr(a.error)}
  </div>
{/each}

<style>
  .role-strip {
    margin-top: 6px;
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }

  .role-chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 10px;
    font-weight: 500;
    color: var(--text-primary);
    background: var(--bg-inset);
    border: 1px solid var(--border-muted);
    border-radius: var(--radius-sm);
    padding: 1px 6px;
  }

  .role-chip.role-failed {
    border-color: color-mix(in srgb, var(--accent-red) 35%, transparent);
    background: color-mix(in srgb, var(--accent-red) 8%, transparent);
  }

  .role-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .role-dur {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: 9px;
  }

  .role-error {
    margin-top: 4px;
    display: flex;
    align-items: baseline;
    gap: 5px;
    font-size: 11px;
    color: var(--accent-red);
    background: color-mix(in srgb, var(--accent-red) 8%, transparent);
    border-radius: var(--radius-sm);
    padding: 3px 8px;
  }

  .role-error-name {
    font-weight: 600;
    flex-shrink: 0;
  }
</style>
