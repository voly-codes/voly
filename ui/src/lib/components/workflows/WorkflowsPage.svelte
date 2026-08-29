<script lang="ts">
  import { onMount } from 'svelte'
  import { decideWorkflowNode, fetchWorkflow, fetchWorkflows } from '../../api/client.js'
  import { t } from '../../i18n/localeStore.svelte.ts'
  import Spinner from '../shared/Spinner.svelte'

  let workflows = $state<any[]>([])
  let selected = $state<any>(null)
  let loading = $state(true)
  let detailLoading = $state(false)
  let error = $state('')
  let submitting = $state('')

  async function refresh() {
    loading = true
    error = ''
    try { workflows = (await fetchWorkflows()).workflows ?? [] }
    catch (e: any) { error = e?.message ?? String(e) }
    finally { loading = false }
  }

  async function open(planId: string) {
    detailLoading = true
    error = ''
    try { selected = await fetchWorkflow(planId) }
    catch (e: any) { error = e?.message ?? String(e) }
    finally { detailLoading = false }
  }

  async function decide(nodeId: string, decision: 'approve' | 'reject') {
    if (!selected) return
    submitting = nodeId
    error = ''
    try {
      await decideWorkflowNode(selected.plan_id, nodeId, decision)
      selected = await fetchWorkflow(selected.plan_id)
    } catch (e: any) { error = e?.message ?? String(e) }
    finally { submitting = '' }
  }

  function isApprovalNode(step: any) {
    return (step.acceptance ?? []).some((a: any) => a.type === 'human_review')
  }

  function fmtMs(ms: number) {
    if (!ms) return '—'
    return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`
  }

  onMount(refresh)
</script>

<section class="page">
  {#if selected}
    <header>
      <div>
        <button class="back" onclick={() => (selected = null)}>&larr; {t('workflows.back')}</button>
        <h1>{selected.metadata?.workflow_name || selected.plan_id}</h1>
        <p>{selected.plan_id} · {t(`workflows.status.${selected.status}`) || selected.status}</p>
      </div>
      <button onclick={() => open(selected.plan_id)} disabled={detailLoading}>{t('workflows.refresh')}</button>
    </header>
    {#if error}<div class="error">{error}</div>{/if}
    {#if detailLoading}<div class="empty"><Spinner size={22} /> {t('common.loading')}</div>
    {:else}
      <div class="graph">
        {#each selected.steps as step, i}
          <article class:verified={step.status === 'verified'} class:failed={step.status === 'failed'} class:pending={step.status === 'verifying'}>
            <div class="node-head">
              <span class="dot"></span>
              <strong>{step.id}</strong>
              <span class="badge">{t(`workflows.status.${step.status}`) || step.status}</span>
            </div>
            <div class="route">{step.role}{step.model ? ` · ${step.model}` : ''}{step.provider ? `/${step.provider}` : ''}</div>
            {#if step.depends_on?.length}<div class="deps">{t('workflows.deps')}: {step.depends_on.join(', ')}</div>{/if}
            <div class="metrics">{fmtMs(step.duration_ms)} · ${Number(step.cost_usd || 0).toFixed(6)}</div>
            {#if step.error}<div class="node-error">{t('workflows.error')}: {step.error}</div>{/if}
            {#if step.status === 'verifying' && isApprovalNode(step)}
              <div class="actions">
                <button class="reject" disabled={submitting === step.id} onclick={() => decide(step.id, 'reject')}>{t('workflows.reject')}</button>
                <button class="approve" disabled={submitting === step.id} onclick={() => decide(step.id, 'approve')}>{t('workflows.approve')}</button>
              </div>
            {/if}
          </article>
          {#if i < selected.steps.length - 1}<div class="arrow">&darr;</div>{/if}
        {/each}
      </div>
    {/if}
  {:else}
    <header>
      <div><h1>{t('workflows.title')}</h1><p>{t('workflows.subtitle')}</p></div>
      <button onclick={refresh} disabled={loading}>{t('workflows.refresh')}</button>
    </header>
    {#if error}<div class="error">{error}</div>{/if}
    {#if loading}<div class="empty"><Spinner size={22} /> {t('common.loading')}</div>
    {:else if workflows.length === 0}<div class="empty">{t('workflows.empty')}</div>
    {:else}<div class="grid">
      {#each workflows as w}
        <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
        <div class="summary-card" onclick={() => open(w.plan_id)}>
          <div class="top"><span class="name">{w.workflow_name || w.plan_id}</span><span class:pending={w.status === 'running'}>{t(`workflows.status.${w.status}`) || w.status}</span></div>
          <dl>
            <div><dt>{t('workflows.nodes')}</dt><dd>{w.verified}/{w.nodes}</dd></div>
            <div><dt>{t('workflows.cost')}</dt><dd>${Number(w.cost_usd || 0).toFixed(6)}</dd></div>
          </dl>
        </div>
      {/each}
    </div>{/if}
  {/if}
</section>

<style>
  .page { flex: 1; overflow: auto; padding: 24px; background: var(--bg-primary); }
  header { display: flex; justify-content: space-between; align-items: start; margin-bottom: 20px; }
  h1 { margin: 0; font-size: 20px; color: var(--text-primary); }
  p { margin: 4px 0; color: var(--text-muted); font-size: 12px; }
  button { border: 1px solid var(--border-default); padding: 7px 12px; background: var(--bg-surface); color: var(--text-primary); cursor: pointer; }
  button:disabled { opacity: .5; cursor: default; }
  .back { border: none; background: none; padding: 0; margin-bottom: 6px; color: var(--text-muted); font-size: 11px; cursor: pointer; }
  .back:hover { color: var(--text-primary); }

  .grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); }
  .summary-card { border: 2px solid var(--frame-strong); background: var(--bg-surface); padding: 14px; box-shadow: 3px 3px 0 var(--frame-strong); cursor: pointer; }
  .summary-card:hover { transform: translate(-1px, -1px); }
  .top { display: flex; justify-content: space-between; font-size: 12px; text-transform: uppercase; }
  .name { color: var(--text-primary); font-weight: 600; }
  .pending { color: var(--voly-orange); }
  dl { display: flex; gap: 16px; margin: 10px 0 0; font-size: 11px; }
  dt { color: var(--text-muted); } dd { margin: 2px 0 0; color: var(--text-primary); }

  .graph { display: flex; flex-direction: column; gap: 6px; max-width: 520px; }
  .arrow { text-align: center; color: var(--text-muted); font-size: 12px; }
  article:not(.summary-card) { border: 3px solid color-mix(in srgb, var(--voly-ink) 58%, var(--border-default)); background: color-mix(in srgb, var(--voly-paper) 8%, var(--bg-surface)); padding: 10px; display: flex; flex-direction: column; gap: 6px; }
  article.verified { border-color: var(--accent-green); }
  article.failed { border-color: var(--accent-red); }
  article.pending { border-color: var(--voly-orange); }
  .node-head { display: flex; align-items: center; gap: 6px; font-size: 10px; color: var(--text-muted); }
  .node-head strong { flex: 1; font: 600 12px var(--font-mono); color: var(--text-primary); }
  .dot { width: 7px; height: 7px; background: var(--text-muted); }
  .verified .dot { background: var(--accent-green); } .failed .dot { background: var(--accent-red); } .pending .dot { background: var(--voly-orange); }
  .badge { padding: 1px 6px; border: 1px solid var(--border-default); font-size: 9px; text-transform: uppercase; }
  .route, .deps, .metrics { font: 10px var(--font-mono); color: var(--text-secondary); }
  .metrics { color: var(--text-muted); }
  .node-error { color: var(--accent-red); font-size: 10px; word-break: break-word; }
  .actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 4px; }
  .approve { background: var(--accent-green); color: var(--bg-primary); }
  .reject { color: var(--accent-red); }
  .empty, .error { padding: 24px; color: var(--text-muted); display: flex; gap: 8px; justify-content: center; }
  .error { color: var(--accent-red); }
</style>
