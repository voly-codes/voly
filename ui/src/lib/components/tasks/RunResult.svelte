<script>
  import { CpuIcon, ClockIcon, BookOpenIcon, LinkIcon, LayersIcon } from '../../icons.js'
  import PxpipeArtifacts from './PxpipeArtifacts.svelte'
  import WorkReport from './WorkReport.svelte'
  import { installSkill } from '../../api/client.js'

  let { result } = $props()

  let hybridSummary = $derived(
    result?.hybrid && (result.hybrid.executor_roles || result.hybrid.chat_roles)
      ? result.hybrid
      : null
  )

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

  const STATUS_COLOR = {
    success:       'var(--accent-green)',
    billing_error: 'var(--accent-red)',
    not_available: 'var(--accent-amber)',
    skipped:       'var(--text-muted)',
    failed:        'var(--accent-red)',
  }
  const STATUS_LABEL = {
    success:       '✓',
    billing_error: 'billing',
    not_available: 'unavail',
    skipped:       'skip',
    failed:        'fail',
  }
</script>

<div class="run-result">
  <div class="result-header">
    <div class="result-meta">
      {#if result.agent}
        <span class="meta-chip">{result.agent}</span>
      {/if}
      {#if result.model}
        <span class="meta-chip model">{result.model}</span>
      {/if}
      {#if result.executor}
        <span class="meta-chip">{result.executor}</span>
      {/if}
      <span class="meta-chip {result.success ? 'ok' : 'err'}">
        {result.success ? 'completed' : 'failed'}
      </span>
      {#if result.dry_run}
        <span class="meta-chip dry" title="all file changes were rolled back">dry-run</span>
      {/if}
      {#if result.safety_violation}
        <span class="meta-chip err" title={result.safety_violation}>safety</span>
      {/if}
      {#if result.billing_fallback}
        <span class="meta-chip warn" title="billing fallback">→ {result.billing_fallback}</span>
      {/if}
    </div>
    <div class="result-stats">
      {#if result.duration_ms}
        <span class="stat"><ClockIcon size="11" strokeWidth="2" />{(result.duration_ms/1000).toFixed(2)}s</span>
      {/if}
      {#if result.usage}
        <span class="stat"><CpuIcon size="11" strokeWidth="2" />{result.usage.input_tokens}+{result.usage.output_tokens}</span>
      {/if}
      {#if result.cost_usd}
        <span class="stat">${result.cost_usd.toFixed(4)}</span>
      {/if}
      {#if result.num_turns}
        <span class="stat">{result.num_turns} turns</span>
      {/if}
    </div>
  </div>

  {#if result.chain_timelog?.length > 1}
    <div class="chain-timelog">
      <div class="chain-header">
        <LinkIcon size="11" strokeWidth="2" />
        <span>Billing chain</span>
      </div>
      <div class="chain-steps">
        {#each result.chain_timelog as entry, i}
          <div class="chain-step">
            <div class="chain-dot" style="background:{STATUS_COLOR[entry.status] ?? 'var(--text-muted)'}"></div>
            <span class="chain-executor">{entry.executor}</span>
            {#if entry.model}
              <span class="chain-model">{entry.model.split('/').pop()}</span>
            {/if}
            <span class="chain-badge" style="color:{STATUS_COLOR[entry.status] ?? 'var(--text-muted)'}">
              {STATUS_LABEL[entry.status] ?? entry.status}
            </span>
            {#if entry.duration_ms > 0}
              <span class="chain-ms">{(entry.duration_ms/1000).toFixed(1)}s</span>
            {/if}
            {#if i < result.chain_timelog.length - 1}
              <span class="chain-arrow">→</span>
            {/if}
          </div>
        {/each}
      </div>
    </div>
  {/if}

  {#if result.a2a_dispatched && result.a2a_assignments?.length}
    <div class="agents-panel">
      <div class="agents-header">
        <LayersIcon size="11" strokeWidth="2" />
        <span>Multi-agent · {result.a2a_assignments.length} agents</span>
      </div>
      <div class="agents-list">
        {#each result.a2a_assignments as a}
          <div class="agent-row">
            <div class="agent-dot" style="background:{a.ok ? 'var(--accent-green)' : 'var(--accent-red)'}"></div>
            <span class="agent-role">{a.role}</span>
            <span class="agent-tier tier-{a.tier}">{a.tier}</span>
            {#if a.mode}
              <span class="agent-badge mode-{a.mode}">{a.mode}</span>
            {/if}
            {#if a.plan_status}
              <span
                class="agent-badge plan-status plan-{a.plan_status}"
                title={a.plan_verify_ok === false ? 'acceptance failed' : `plan: ${a.plan_status}`}
              >{a.plan_status}</span>
            {/if}
            {#if a.mode === 'executor' && a.executor}
              <span class="agent-model">{a.executor}</span>
            {:else}
              <span class="agent-model">{a.provider}/{a.model?.split('/').pop()}</span>
            {/if}
            {#if a.files_touched?.length}
              <span class="agent-badge files" title={a.files_touched.join('\n')}>{a.files_touched.length} files</span>
            {/if}
            {#if a.cache_hit}
              <span class="agent-badge cached">cached</span>
            {/if}
            {#if a.mem_hits}
              <span class="agent-badge mem">mem {a.mem_hits}</span>
            {/if}
            <div class="agent-skills">
              {#each a.skills ?? [] as s}
                <span class="agent-skill">{s}</span>
              {/each}
            </div>
            <span class="agent-tokens">{a.input_tokens}+{a.output_tokens}</span>
            {#if a.cost_usd}
              <span class="agent-cost">${a.cost_usd.toFixed(4)}</span>
            {/if}
          </div>
        {/each}
      </div>
    </div>
  {/if}

  {#if hybridSummary}
    <div class="hybrid-summary">
      <LayersIcon size="11" strokeWidth="2" />
      <span>Hybrid:</span>
      <span class="hy-stat">{hybridSummary.executor_roles ?? 0} executor</span>
      <span class="hy-sep">·</span>
      <span class="hy-stat">{hybridSummary.chat_roles ?? 0} chat</span>
      {#if hybridSummary.files_touched?.length}
        <span class="hy-sep">·</span>
        <span class="hy-stat" title={hybridSummary.files_touched.join('\n')}>
          {hybridSummary.files_touched.length} files
        </span>
      {/if}
    </div>
  {/if}

  <WorkReport report={result.report} />
  <PxpipeArtifacts artifacts={result.artifacts} />

  {#if result.safety_rolled_back?.length}
    <div class="safety-note">
      rolled back: {result.safety_rolled_back.join(', ')}
    </div>
  {/if}

  {#if result.dry_run_diff}
    <details class="diff-block">
      <summary>Diff preview (dry-run — changes were rolled back)</summary>
      <pre class="diff-content">{result.dry_run_diff}</pre>
    </details>
  {/if}

  {#if result.injected_skills?.length}
    <div class="injected-skills">
      <BookOpenIcon size="11" strokeWidth="2" />
      <span class="injected-label">Skills:</span>
      {#each result.injected_skills as sid}
        <span class="skill-chip">{sid}</span>
      {/each}
    </div>
  {/if}

  {#if result.skill_suggestions?.length}
    <div class="skill-suggest-banner">
      <div class="suggest-header">
        <BookOpenIcon size="11" strokeWidth="2" />
        <span>Relevant skills found in marketplace — install to improve future runs</span>
      </div>
      <div class="suggest-list">
        {#each result.skill_suggestions as s}
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

  {#if result.content}
    <pre class="result-content">{result.content}</pre>
  {/if}

  {#if result.error}
    <div class="result-err-msg">{result.error}</div>
  {/if}
</div>

<style>
  .run-result {
    background: var(--bg-inset);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    overflow: hidden;
  }

  .result-header {
    padding: 8px 10px;
    border-bottom: 1px solid var(--border-muted);
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }

  .result-meta { display: flex; gap: 4px; flex-wrap: wrap; flex: 1; }

  .meta-chip {
    font-size: 10px;
    font-weight: 500;
    padding: 1px 6px;
    border-radius: var(--radius-sm);
    background: var(--bg-surface);
    border: 1px solid var(--border-default);
    color: var(--text-secondary);
  }
  .meta-chip.model { color: var(--accent-purple); border-color: color-mix(in srgb, var(--accent-purple) 30%, transparent); }
  .meta-chip.ok { color: var(--accent-green); border-color: color-mix(in srgb, var(--accent-green) 30%, transparent); }
  .meta-chip.err { color: var(--accent-red); border-color: color-mix(in srgb, var(--accent-red) 30%, transparent); }
  .meta-chip.dry,
  .meta-chip.warn { color: var(--accent-amber); border-color: color-mix(in srgb, var(--accent-amber) 30%, transparent); }

  .hybrid-summary {
    display: flex;
    align-items: center;
    gap: 5px;
    padding: 6px 10px;
    border-bottom: 1px solid var(--border-muted);
    font-size: 11px;
    color: var(--text-secondary);
  }
  .hy-stat { font-variant-numeric: tabular-nums; }
  .hy-sep { color: var(--text-muted); }

  .safety-note {
    padding: 6px 10px;
    border-bottom: 1px solid var(--border-muted);
    font-size: 10.5px;
    font-family: var(--font-mono);
    color: var(--accent-amber);
    word-break: break-all;
  }

  .diff-block {
    border-bottom: 1px solid var(--border-muted);
  }
  .diff-block summary {
    padding: 6px 10px;
    font-size: 11px;
    color: var(--text-secondary);
    cursor: pointer;
    user-select: none;
  }
  .diff-block summary:hover { color: var(--text-primary); }
  .diff-content {
    margin: 0;
    padding: 8px 10px;
    max-height: 320px;
    overflow: auto;
    font-size: 10.5px;
    font-family: var(--font-mono);
    line-height: 1.5;
    color: var(--text-secondary);
    background: var(--bg-surface);
    white-space: pre;
  }

  .result-stats {
    display: flex;
    gap: 8px;
    align-items: center;
    flex-shrink: 0;
  }

  .stat {
    display: flex;
    align-items: center;
    gap: 3px;
    font-size: 11px;
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
  }

  .chain-timelog {
    border-bottom: 1px solid var(--border-muted);
    padding: 6px 10px;
  }

  .chain-header {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 9px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-muted);
    margin-bottom: 5px;
  }

  .chain-steps {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 4px;
  }

  .chain-step {
    display: flex;
    align-items: center;
    gap: 3px;
  }

  .chain-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .chain-executor {
    font-size: 10px;
    font-weight: 500;
    color: var(--text-secondary);
    font-family: var(--font-mono);
  }

  .chain-model {
    font-size: 9px;
    color: var(--text-muted);
    font-family: var(--font-mono);
  }

  .chain-badge {
    font-size: 9px;
    font-weight: 600;
  }

  .chain-ms {
    font-size: 9px;
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
  }

  .chain-arrow {
    font-size: 10px;
    color: var(--text-muted);
    margin: 0 1px;
  }

  .agents-panel {
    border-bottom: 1px solid var(--border-muted);
    padding: 6px 10px;
  }

  .agents-header {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 9px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-muted);
    margin-bottom: 6px;
  }

  .agents-list {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .agent-row {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
  }

  .agent-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .agent-role {
    font-size: 11px;
    font-weight: 600;
    color: var(--text-secondary);
    min-width: 68px;
  }

  .agent-tier {
    font-size: 9px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    padding: 1px 5px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-default);
    color: var(--text-muted);
  }
  .agent-tier.tier-premium {
    color: var(--accent-purple);
    border-color: color-mix(in srgb, var(--accent-purple) 30%, transparent);
    background: color-mix(in srgb, var(--accent-purple) 10%, transparent);
  }
  .agent-tier.tier-standard {
    color: var(--accent-teal);
    border-color: color-mix(in srgb, var(--accent-teal) 30%, transparent);
    background: color-mix(in srgb, var(--accent-teal) 10%, transparent);
  }
  .agent-tier.tier-cheap {
    color: var(--accent-amber);
    border-color: color-mix(in srgb, var(--accent-amber) 30%, transparent);
    background: color-mix(in srgb, var(--accent-amber) 10%, transparent);
  }

  .agent-model {
    font-size: 10px;
    font-family: var(--font-mono);
    color: var(--text-muted);
  }

  .agent-badge {
    font-size: 9px;
    font-weight: 600;
    padding: 0 5px;
    border-radius: var(--radius-sm);
  }
  .agent-badge.mode-executor {
    color: var(--accent-blue, #3b82f6);
    background: color-mix(in srgb, var(--accent-blue, #3b82f6) 12%, transparent);
    border: 1px solid color-mix(in srgb, var(--accent-blue, #3b82f6) 30%, transparent);
  }
  .agent-badge.mode-chat {
    color: var(--text-muted, #94a3b8);
    background: color-mix(in srgb, var(--text-muted, #94a3b8) 10%, transparent);
    border: 1px solid color-mix(in srgb, var(--text-muted, #94a3b8) 25%, transparent);
  }
  .agent-badge.files {
    color: var(--accent-orange, #f59e0b);
    background: color-mix(in srgb, var(--accent-orange, #f59e0b) 12%, transparent);
    border: 1px solid color-mix(in srgb, var(--accent-orange, #f59e0b) 30%, transparent);
  }
  .agent-badge.cached {
    color: var(--accent-green);
    background: color-mix(in srgb, var(--accent-green) 12%, transparent);
    border: 1px solid color-mix(in srgb, var(--accent-green) 30%, transparent);
  }
  .agent-badge.mem {
    color: var(--accent-blue, var(--accent-purple));
    background: color-mix(in srgb, var(--accent-purple) 12%, transparent);
    border: 1px solid color-mix(in srgb, var(--accent-purple) 30%, transparent);
  }
  .agent-badge.plan-status {
    text-transform: lowercase;
    border: 1px solid var(--border-default);
    color: var(--text-muted);
  }
  .agent-badge.plan-verified {
    color: var(--accent-green);
    border-color: color-mix(in srgb, var(--accent-green) 30%, transparent);
    background: color-mix(in srgb, var(--accent-green) 10%, transparent);
  }
  .agent-badge.plan-failed,
  .agent-badge.plan-blocked {
    color: var(--accent-red);
    border-color: color-mix(in srgb, var(--accent-red) 30%, transparent);
    background: color-mix(in srgb, var(--accent-red) 10%, transparent);
  }
  .agent-badge.plan-running,
  .agent-badge.plan-verifying {
    color: var(--accent-amber, #f59e0b);
    border-color: color-mix(in srgb, var(--accent-amber, #f59e0b) 30%, transparent);
    background: color-mix(in srgb, var(--accent-amber, #f59e0b) 10%, transparent);
  }

  .agent-skills {
    display: flex;
    gap: 3px;
    flex-wrap: wrap;
    flex: 1;
  }

  .agent-skill {
    font-size: 9px;
    font-family: var(--font-mono);
    background: color-mix(in srgb, var(--accent-teal) 12%, transparent);
    border: 1px solid color-mix(in srgb, var(--accent-teal) 30%, transparent);
    color: var(--accent-teal);
    border-radius: var(--radius-sm);
    padding: 0 5px;
  }

  .agent-tokens {
    font-size: 9px;
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
  }

  .agent-cost {
    font-size: 10px;
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
    min-width: 52px;
    text-align: right;
  }

  .injected-skills {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 4px;
    padding: 6px 10px;
    border-bottom: 1px solid var(--border-muted);
    color: var(--accent-teal);
    font-size: 11px;
  }

  .injected-label {
    font-weight: 500;
    margin-right: 2px;
  }

  .skill-chip {
    font-size: 10px;
    font-family: var(--font-mono);
    background: color-mix(in srgb, var(--accent-teal) 12%, transparent);
    border: 1px solid color-mix(in srgb, var(--accent-teal) 30%, transparent);
    color: var(--accent-teal);
    border-radius: var(--radius-sm);
    padding: 1px 5px;
  }

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

  .result-content {
    padding: 12px;
    font-size: 12px;
    font-family: var(--font-mono);
    color: var(--text-primary);
    white-space: pre-wrap;
    word-break: break-word;
    max-height: none;
    overflow-y: visible;
    line-height: 1.6;
  }

  .result-err-msg {
    padding: 8px 12px;
    font-size: 12px;
    color: var(--accent-red);
  }
</style>
