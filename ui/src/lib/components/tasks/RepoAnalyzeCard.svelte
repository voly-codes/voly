<script>
  import Spinner from '../shared/Spinner.svelte'
  import { analyzeRepo } from '../../api/client.js'

  let {
    repo_url = $bindable(''),
    running = false,
  } = $props()

  let analyzing = $state(false)
  let intel = $state(null)
  let error = $state(null)

  async function runAnalyze() {
    const url = repo_url.trim()
    if (!url || analyzing || running) return
    analyzing = true
    error = null
    intel = null
    try {
      const data = await analyzeRepo(url)
      if (data?.error) {
        error = data.error
      } else {
        intel = data
      }
    } catch (e) {
      error = e.message
    } finally {
      analyzing = false
    }
  }
</script>

<div class="repo-analyze">
  <button
    type="button"
    class="analyze-btn"
    onclick={runAnalyze}
    disabled={running || analyzing || !repo_url.trim()}
  >
    {#if analyzing}
      <Spinner size={12} strokeWidth={2} />
      Analyzing…
    {:else}
      Analyze
    {/if}
  </button>

  {#if error}
    <p class="analyze-error">{error}</p>
  {/if}

  {#if intel}
    <div class="intel-card">
      <div class="intel-row">
        <span class="intel-key">Languages</span>
        <span>{(intel.stack?.languages ?? []).join(', ') || '—'}</span>
      </div>
      <div class="intel-row">
        <span class="intel-key">Frameworks</span>
        <span>{(intel.stack?.frameworks ?? []).join(', ') || '—'}</span>
      </div>
      <div class="intel-row">
        <span class="intel-key">License</span>
        <span>{intel.license?.spdx ?? 'unknown'} ({intel.license?.risk ?? 'unknown'} risk)</span>
      </div>
      <div class="intel-row">
        <span class="intel-key">Security</span>
        <span>{(intel.risks ?? []).length} issues</span>
      </div>
      <div class="intel-row">
        <span class="intel-key">Quality</span>
        <span>{Math.round((intel.quality?.maintainability_score ?? 0) * 100)}%</span>
      </div>
    </div>
  {/if}
</div>

<style>
  .repo-analyze {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-top: 4px;
  }

  .analyze-btn {
    align-self: flex-start;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    height: 26px;
    padding: 0 10px;
    font-size: 11px;
    font-weight: 600;
    color: var(--text-secondary);
    background: var(--bg-surface);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
  }
  .analyze-btn:hover:not(:disabled) {
    border-color: var(--accent-blue);
    color: var(--text-primary);
  }
  .analyze-btn:disabled { opacity: 0.5; cursor: not-allowed; }

  .analyze-error {
    margin: 0;
    font-size: 11px;
    color: var(--accent-red);
  }

  .intel-card {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 8px 10px;
    font-size: 11px;
    color: var(--text-secondary);
    background: color-mix(in srgb, var(--bg-inset) 50%, transparent);
    border: 1px solid var(--border-muted);
    border-radius: var(--radius-sm);
  }

  .intel-row {
    display: flex;
    gap: 8px;
    line-height: 1.35;
  }

  .intel-key {
    flex-shrink: 0;
    width: 72px;
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    color: var(--text-muted);
  }
</style>
