<script>
  import { t } from '../../i18n/localeStore.svelte.ts'
  import ExtrasSection from './ExtrasSection.svelte'
  import InspectorBillingChain from './InspectorBillingChain.svelte'

  let { task } = $props()
</script>

{#if task.gateway}
  {@const gw = task.gateway}
  <ExtrasSection title={t("inspector.gateway")}>
    <div class="extras-grid">
      <div class="extra-row"><span class="extra-k">{t('inspector.cache')}</span><span class="extra-v" class:ok={gw.cache_hit} class:muted={!gw.cache_hit}>{gw.cache_hit ? t('inspector.cacheHit') : t('inspector.cacheMiss')}</span></div>
      <div class="extra-row">
        <span class="extra-k">{t('inspector.fallback')}</span>
        <span class="extra-v" class:warn={gw.fallback_used} class:muted={!gw.fallback_used}>
          {#if gw.fallback_used}
            {t('inspector.fallbackUsed')} {gw.fallback_model || '?'}{gw.fallback_provider ? ` (${gw.fallback_provider})` : ''}
          {:else}
            {t('inspector.fallbackNotNeeded')}
          {/if}
        </span>
      </div>
      {#if gw.fallback_used && gw.fallback_reason}
        <div class="extra-row fallback-reason-row">
          <span class="extra-k">{t('inspector.reason')}</span>
          <span class="extra-v err fallback-reason" title={gw.fallback_reason}>{gw.fallback_reason}</span>
        </div>
      {/if}
      <div class="extra-row"><span class="extra-k">DLP</span><span class="extra-v" class:err={gw.dlp_blocked} class:muted={!gw.dlp_blocked}>{gw.dlp_blocked ? t('inspector.dlpBlocked') : t('inspector.dlpPassed')}</span></div>
      {#if task.provider}
        <div class="extra-row"><span class="extra-k">{t('inspector.provider')}</span><span class="extra-v">{task.provider}</span></div>
      {/if}
    </div>
  </ExtrasSection>
{/if}

<InspectorBillingChain chain_timelog={task.chain_timelog} />

{#if task.dspy_enabled}
  <ExtrasSection title="DSPy">
    <div class="extras-grid">
      <div class="extra-row"><span class="extra-k">{t('inspector.mode')}</span><span class="extra-v">{task.dspy_mode ?? '—'}</span></div>
      {#if task.dspy_program_id}<div class="extra-row"><span class="extra-k">{t('inspector.program')}</span><span class="extra-v mono">{task.dspy_program_id}</span></div>{/if}
      {#if task.dspy_program_version}<div class="extra-row"><span class="extra-k">{t('inspector.version')}</span><span class="extra-v">v{task.dspy_program_version}</span></div>{/if}
      {#if task.dspy_program_tag}<div class="extra-row"><span class="extra-k">{t('inspector.tag')}</span><span class="extra-v">{task.dspy_program_tag}</span></div>{/if}
      {#if task.dspy_score != null}<div class="extra-row"><span class="extra-k">Score</span><span class="extra-v ok">{(task.dspy_score * 100).toFixed(1)}%</span></div>{/if}
      {#if task.dspy_shadow_delta != null}<div class="extra-row"><span class="extra-k">Shadow delta</span><span class="extra-v">{task.dspy_shadow_delta > 0 ? '+' : ''}{task.dspy_shadow_delta.toFixed(3)}</span></div>{/if}
    </div>
  </ExtrasSection>
{/if}

<ExtrasSection title={t('inspector.metadata')}>
  <div class="extras-grid">
    <div class="extra-row"><span class="extra-k">Task ID</span><span class="extra-v mono">{task.task_id}</span></div>
    {#if task.task_type}<div class="extra-row"><span class="extra-k">{t('inspector.type')}</span><span class="extra-v">{task.task_type}</span></div>{/if}
    {#if task.routing_score}<div class="extra-row"><span class="extra-k">Routing</span><span class="extra-v">{(task.routing_score * 100).toFixed(1)}%</span></div>{/if}
    {#if task.automation_score}<div class="extra-row"><span class="extra-k">{t('inspector.automation')}</span><span class="extra-v">{(task.automation_score * 100).toFixed(0)}%</span></div>{/if}
    {#if task.manual_steps_removed}<div class="extra-row"><span class="extra-k">{t('inspector.stepsRemoved')}</span><span class="extra-v ok">{task.manual_steps_removed}</span></div>{/if}
    {#if task.skill_ids?.length}<div class="extra-row"><span class="extra-k">{t('inspector.skills')}</span><span class="extra-v mono">{task.skill_ids.join(', ')}</span></div>{/if}
  </div>
</ExtrasSection>

<style>
  .extras-grid { display: flex; flex-direction: column; gap: 3px; }

  .extra-row {
    display: flex;
    align-items: baseline;
    gap: 8px;
    font-size: 11px;
  }

  .extra-k {
    width: 110px;
    flex-shrink: 0;
    color: var(--text-muted);
    font-size: 10px;
  }

  .extra-v {
    color: var(--text-secondary);
    font-variant-numeric: tabular-nums;
  }

  .extra-v.mono { font-family: var(--font-mono); font-size: 10px; word-break: break-all; }
  .extra-v.ok   { color: var(--accent-green); }
  .extra-v.warn { color: var(--accent-amber); }
  .extra-v.err  { color: var(--accent-red); }
  .extra-v.muted { color: var(--text-muted); }

  .fallback-reason {
    font-size: 10px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 200px;
    cursor: help;
  }
</style>
