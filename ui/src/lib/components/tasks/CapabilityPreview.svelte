<script>
  import { onMount } from 'svelte'
  import { ZapIcon } from '../../icons.js'
  import { matchCapability } from '../../api/client.js'

  const API_BASE = import.meta.env.VITE_VOLY_API_BASE_URL ?? ''

  let {
    task = '',
    executor = '',
    dimension = 'backend',
    onUse = undefined,
  } = $props()

  let loading = $state(false)
  let registryEmpty = $state(true)
  let match = $state(null)

  onMount(async () => {
    try {
      const resp = await fetch(`${API_BASE}/api/capability/profiles`)
      const data = await resp.json()
      registryEmpty = !(data?.executor_ids?.length > 0)
    } catch {
      registryEmpty = true
    }
  })

  let debounceTimer
  $effect(() => {
    const t = task.trim()
    if (debounceTimer) clearTimeout(debounceTimer)
    if (registryEmpty || !t) {
      match = null
      return
    }
    debounceTimer = setTimeout(async () => {
      loading = true
      try {
        const available = executor ? [executor] : undefined
        match = await matchCapability(dimension, available, undefined)
      } catch {
        match = null
      } finally {
        loading = false
      }
    }, 600)
    return () => clearTimeout(debounceTimer)
  })

  const recommended = $derived(match?.recommended ?? null)
  const fallbacks = $derived((match?.fallbacks ?? []).slice(0, 2))
  const showBar = $derived(!registryEmpty && !loading && recommended)
  const scorePct = $derived(
    recommended ? Math.round((recommended.routing_score ?? recommended.score ?? 0) * 100) : 0,
  )
</script>

{#if showBar}
  <div class="cap-bar">
    <ZapIcon size="11" strokeWidth="2" />
    <span class="cap-label">
      Best match:
      <span class="cap-score">{recommended.executor_id} ({scorePct}%)</span>
    </span>
    {#if recommended.executor_id !== executor}
      <button type="button" class="cap-use" onclick={() => onUse?.(recommended.executor_id)}>
        Use
      </button>
    {/if}
    {#each fallbacks as fb}
      <span class="cap-fallback">{fb.executor_id} {Math.round((fb.routing_score ?? fb.score ?? 0) * 100)}%</span>
    {/each}
  </div>
{/if}

<style>
  .cap-bar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
    margin-top: 4px;
    padding: 4px 8px;
    font-size: 10px;
    color: var(--text-muted);
    background: color-mix(in srgb, var(--bg-inset) 60%, transparent);
    border: 1px solid var(--border-muted);
    border-radius: var(--radius-sm);
  }

  .cap-label { line-height: 1.3; }

  .cap-score {
    font-family: var(--font-mono);
    color: var(--accent-blue);
    font-weight: 600;
  }

  .cap-use {
    padding: 1px 6px;
    font-size: 10px;
    font-weight: 600;
    color: var(--accent-blue);
    border: 1px solid color-mix(in srgb, var(--accent-blue) 35%, transparent);
    border-radius: 4px;
    background: color-mix(in srgb, var(--accent-blue) 10%, transparent);
  }
  .cap-use:hover { opacity: 0.85; }

  .cap-fallback {
    font-family: var(--font-mono);
    font-size: 9px;
    padding: 1px 5px;
    border-radius: 4px;
    background: var(--bg-surface);
    border: 1px solid var(--border-default);
    color: var(--text-secondary);
  }
</style>
