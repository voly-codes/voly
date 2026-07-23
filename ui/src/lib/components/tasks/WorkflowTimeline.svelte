<script>
  let { entries = [], stopReason = '' } = $props()
</script>

<div class="timeline">
  <div class="title">Causal timeline</div>
  {#if entries.length}
    {#each entries as entry, index}
      <div class="event">
        <span class="index">{index + 1}</span>
        <span class="lap">lap {entry.lap ?? '—'}</span>
        <span class="route">{entry.from ?? 'start'} → {entry.to ?? 'stop'}</span>
        <span class="reason">{entry.reason ?? 'transition'}</span>
      </div>
    {/each}
  {:else}
    <div class="empty">Waiting for the first transition…</div>
  {/if}
  {#if stopReason}
    <div class="stop"><span>stop</span><strong>{stopReason}</strong></div>
  {/if}
</div>

<style>
  .timeline { display: flex; flex-direction: column; gap: 5px; }
  .title { font-size: 10px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; }
  .event { display: grid; grid-template-columns: 18px 42px minmax(120px, 1fr) minmax(120px, 1fr); gap: 6px; align-items: center; font-size: 10px; color: var(--text-secondary); }
  .index { width: 16px; height: 16px; display: grid; place-items: center; border-radius: 50%; background: var(--bg-inset); border: 1px solid var(--border-default); font-size: 9px; }
  .lap, .route { font-family: var(--font-mono); }
  .route { color: var(--text-primary); }
  .reason { color: var(--text-muted); word-break: break-word; }
  .empty { font-size: 10px; color: var(--text-muted); }
  .stop { display: flex; gap: 8px; padding-top: 5px; margin-top: 2px; border-top: 1px solid var(--border-muted); font-size: 10px; color: var(--text-muted); }
  .stop strong { color: var(--text-primary); font-family: var(--font-mono); }
  @media (max-width: 700px) { .event { grid-template-columns: 18px 42px 1fr; } .reason { grid-column: 3; } }
</style>
