<script lang="ts">
  import { onMount } from 'svelte'
  import { fetchDecisions, submitDecision } from '../../api/client.js'
  import { t } from '../../i18n/localeStore.svelte.ts'
  import Spinner from '../shared/Spinner.svelte'

  let decisions = $state<any[]>([])
  let loading = $state(true)
  let error = $state('')
  let submitting = $state('')

  async function refresh() {
    loading = true
    error = ''
    try { decisions = (await fetchDecisions()).decisions ?? [] }
    catch (e: any) { error = e?.message ?? String(e) }
    finally { loading = false }
  }

  async function decide(planId: string, value: 'approve' | 'reject') {
    submitting = planId
    error = ''
    try { await submitDecision(planId, value); await refresh() }
    catch (e: any) { error = e?.message ?? String(e) }
    finally { submitting = '' }
  }

  onMount(refresh)
</script>

<section class="page">
  <header>
    <div><h1>{t('decisions.title')}</h1><p>{t('decisions.subtitle')}</p></div>
    <button onclick={refresh} disabled={loading}>{t('decisions.refresh')}</button>
  </header>
  {#if error}<div class="error">{error}</div>{/if}
  {#if loading}<div class="empty"><Spinner size={22} /> {t('common.loading')}</div>
  {:else if decisions.length === 0}<div class="empty">{t('decisions.empty')}</div>
  {:else}<div class="grid">
    {#each decisions as plan}
      {@const meta = plan.metadata ?? {}}
      <article>
        <div class="top"><span class="urgency">{meta.urgency}</span><span class:pending={meta.decision === 'pending'}>{t(`decisions.${meta.decision ?? 'pending'}`)}</span></div>
        <h2>{plan.task}</h2><p>{meta.rationale}</p>
        {#if meta.estimated_impact}<dl><dt>{t('decisions.impact')}</dt><dd>{meta.estimated_impact}</dd></dl>{/if}
        {#if meta.decision === 'pending'}<div class="actions">
          <button class="reject" disabled={submitting === plan.plan_id} onclick={() => decide(plan.plan_id, 'reject')}>{t('decisions.reject')}</button>
          <button class="approve" disabled={submitting === plan.plan_id} onclick={() => decide(plan.plan_id, 'approve')}>{t('decisions.approve')}</button>
        </div>{/if}
      </article>
    {/each}
  </div>{/if}
</section>

<style>
  .page { flex: 1; overflow: auto; padding: 24px; background: var(--bg-primary); }
  header { display: flex; justify-content: space-between; align-items: start; margin-bottom: 20px; }
  h1 { margin: 0; font-size: 20px; color: var(--text-primary); } h2 { font-size: 15px; margin: 12px 0 6px; }
  p { margin: 4px 0; color: var(--text-muted); font-size: 12px; }
  button { border: 1px solid var(--border-default); padding: 7px 12px; background: var(--bg-surface); color: var(--text-primary); cursor: pointer; }
  button:disabled { opacity: .5; cursor: default; }
  .grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); }
  article { border: 2px solid var(--frame-strong); background: var(--bg-surface); padding: 14px; box-shadow: 3px 3px 0 var(--frame-strong); }
  .top, .actions { display: flex; justify-content: space-between; gap: 8px; font-size: 11px; text-transform: uppercase; }
  .urgency, .pending { color: var(--voly-orange); } dl { font-size: 12px; } dt { color: var(--text-muted); } dd { margin: 3px 0; }
  .actions { justify-content: flex-end; margin-top: 14px; } .approve { background: var(--accent-green); color: var(--bg-primary); } .reject { color: var(--accent-red); }
  .empty, .error { padding: 24px; color: var(--text-muted); display: flex; gap: 8px; justify-content: center; } .error { color: var(--accent-red); }
</style>
