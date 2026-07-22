<script>
  import { i18n, t } from '../../i18n/localeStore.svelte.ts'
  import { tasksStore } from '../../stores/tasksStore.svelte'
  import PipelineEmptyState from './PipelineEmptyState.svelte'
  import TaskHeader from './TaskHeader.svelte'
  import PipelineStages from './PipelineStages.svelte'
  import StatsOverview from './StatsOverview.svelte'
  import WorkReport from './WorkReport.svelte'
  import ExtrasSection from './ExtrasSection.svelte'
  import PxpipeArtifacts from './PxpipeArtifacts.svelte'
  import InspectorAgentsList from './InspectorAgentsList.svelte'
  import InspectorMetaSections from './InspectorMetaSections.svelte'
  import { buildPipelineStages, buildTokenBar } from './pipelineStageModel.js'
  import AgentAtlas from './AgentAtlas.svelte'

  let outputExpanded = $state(true)
  let task = $derived(tasksStore.selected)
  let activeTab = $state('report')

  // Reset to the report tab whenever a different task is selected, so the
  // atlas of a previous task doesn't linger under a new one.
  $effect(() => { void task?.task_id; activeTab = 'report' })

  let tokenBar = $derived.by(() => {
    void i18n.locale
    return buildTokenBar(task, t)
  })

  let stages = $derived.by(() => {
    void i18n.locale
    return buildPipelineStages(task, t)
  })
</script>

{#if !task}
  <PipelineEmptyState />
{:else}
  <div class="inspector">
    <TaskHeader {task} />

    <div class="inspector-tabs">
      <button
        type="button"
        class="inspector-tab"
        class:active={activeTab === 'report'}
        onclick={() => activeTab = 'report'}
      >{t('inspector.tabReport')}</button>
      <button
        type="button"
        class="inspector-tab"
        class:active={activeTab === 'atlas'}
        onclick={() => activeTab = 'atlas'}
      >{t('inspector.tabAtlas')}</button>
    </div>

    {#if activeTab === 'atlas'}
      <AgentAtlas {task} />
    {:else}
    <div class="inspector-body">
      <div class="left-pane">
        <PipelineStages {stages} />
      </div>

      <div class="right-pane">
        {#if task.task_prompt}
          <div class="task-prompt-field">
            <span class="task-prompt-label">{t('inspector.task')}</span>
            <div class="task-prompt-text">{task.task_prompt}</div>
          </div>
        {/if}

        <StatsOverview
          costUsd={task.cost_usd ?? 0}
          inputTokens={task.tokens?.input ?? 0}
          outputTokens={task.tokens?.output ?? 0}
          savedTokens={(task.tokens?.saved_rtk ?? 0) + (task.tokens?.saved_headroom ?? 0)}
          durationMs={task.duration_ms}
          routingScore={task.routing_score}
          {tokenBar}
        />

        <WorkReport report={task.report} />
        <PxpipeArtifacts artifacts={task.artifacts} />

        <div class="right-sections">
          {#if task.result}
            <ExtrasSection title={t("inspector.output")} chip="{(task.tokens?.output ?? 0).toLocaleString()} tok" collapsible bind:expanded={outputExpanded}>
              <div class="text-block output-block">{task.result}</div>
            </ExtrasSection>
          {/if}

          {#if task.a2a_dispatched && task.a2a_assignments?.length}
            <InspectorAgentsList assignments={task.a2a_assignments} live={!!task._live} />
          {/if}

          <InspectorMetaSections {task} />
        </div>
      </div>
    </div>
    {/if}
  </div>
{/if}

<style>
  .inspector-tabs {
    display: flex;
    gap: 2px;
    padding: 6px 14px 0;
    border-bottom: 1px solid var(--border-default);
    flex-shrink: 0;
  }

  .inspector-tab {
    padding: 6px 12px;
    font-size: 12px;
    font-weight: 500;
    color: var(--text-muted);
    border-bottom: 2px solid transparent;
    margin-bottom: -1px;
    transition: color 0.12s, border-color 0.12s;
  }

  .inspector-tab:hover { color: var(--text-primary); }
  .inspector-tab.active { color: var(--text-primary); border-bottom-color: var(--accent-blue); }

  .inspector {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .inspector-body {
    flex: 1;
    display: flex;
    overflow: hidden;
  }

  .left-pane {
    flex: 1;
    min-width: 0;
    border-right: 1px solid var(--border-default);
    overflow-y: auto;
    padding: 14px 14px 14px 16px;
    display: flex;
    flex-direction: column;
  }

  .right-pane {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .right-sections {
    flex: 1;
    overflow-y: auto;
    padding: 0 16px 16px;
  }

  .task-prompt-field {
    padding: 10px 14px 8px;
    border-bottom: 1px solid var(--border-default);
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    gap: 5px;
  }

  .task-prompt-label {
    font-size: 9px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-muted);
  }

  .task-prompt-text {
    font-size: 12px;
    color: var(--text-primary);
    line-height: 1.5;
    white-space: pre-wrap;
    word-break: break-word;
    max-height: 120px;
    overflow-y: auto;
    background: var(--bg-inset);
    border: 1px solid var(--border-muted);
    border-radius: var(--radius-sm);
    padding: 6px 8px;
  }

  .text-block {
    margin-top: 7px;
    font-size: 11px;
    color: var(--text-secondary);
    line-height: 1.55;
    white-space: pre-wrap;
    word-break: break-word;
    background: var(--bg-inset);
    border-radius: var(--radius-sm);
    padding: 8px 10px;
    border: 1px solid var(--border-muted);
    max-height: 200px;
    overflow-y: auto;
  }

  .output-block {
    font-family: var(--font-mono);
    font-size: 10.5px;
    max-height: 300px;
  }
</style>
