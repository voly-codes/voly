<script>
  import { BookOpenIcon, FolderIcon, LayersIcon } from '../../icons.js'
  import BillingChainTimelog from './BillingChainTimelog.svelte'
  import MultiAgentPanel from './MultiAgentPanel.svelte'
  import PxpipeArtifacts from './PxpipeArtifacts.svelte'
  import RunResultHeader from './RunResultHeader.svelte'
  import SkillSuggestBanner from './SkillSuggestBanner.svelte'
  import WorkReport from './WorkReport.svelte'

  let { result } = $props()
</script>

<div class="run-result">
  <RunResultHeader {result} />

  <BillingChainTimelog chain_timelog={result.chain_timelog} />

  <MultiAgentPanel
    assignments={result.a2a_dispatched ? (result.a2a_assignments ?? []) : []}
    hybrid={result.hybrid}
  />

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

  {#if result.greenfield && result.project_dir}
    <div class="greenfield-notice">
      <FolderIcon size="11" strokeWidth="2" />
      <span>New project created at <code>{result.project_dir}</code></span>
    </div>
  {/if}

  {#if result.tech_stack?.length}
    <div class="injected-skills">
      <LayersIcon size="11" strokeWidth="2" />
      <span class="injected-label">Tech stack:</span>
      {#each result.tech_stack as item}
        <span class="skill-chip">{item.label} {item.version}</span>
      {/each}
    </div>
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

  <SkillSuggestBanner suggestions={result.skill_suggestions} />

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

  .greenfield-notice {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 10px;
    border-bottom: 1px solid var(--border-muted);
    font-size: 11px;
    color: var(--accent-teal);
  }

  .greenfield-notice code {
    font-family: var(--font-mono);
    font-size: 10.5px;
    background: color-mix(in srgb, var(--accent-teal) 12%, transparent);
    padding: 1px 4px;
    border-radius: 3px;
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
