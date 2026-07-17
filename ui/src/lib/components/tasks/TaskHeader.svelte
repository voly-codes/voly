<script>
  import { AlertCircleIcon } from '../../icons.js'
  import RoleStrip from './RoleStrip.svelte'
  import { fmtRel, statusRu } from './lib/utils.js'
  import { t } from '../../i18n/localeStore.svelte.ts'

  let { task } = $props()
</script>

<div class="inspector-header">
  <div class="header-top">
    <div class="task-title">
      <span class="task-id">{task.task_id?.slice(0, 8)}</span>
      {#if task.workflow}
        <span class="task-workflow">{task.workflow}</span>
      {/if}
      <span class="task-status status-{task.status}">{statusRu[task.status] ?? task.status}</span>
    </div>
    <span class="task-time">{fmtRel(task._mtime)}</span>
  </div>

  <div class="meta-strip">
    {#if task.agent}
      <span class="meta-badge meta-agent"><span class="meta-k">{t('meta.agent')}</span><span class="meta-v">{task.agent}</span></span>
    {/if}
    {#if task.model}
      <span class="meta-badge meta-model"><span class="meta-k">{t('meta.model')}</span><span class="meta-v">{task.model}</span></span>
    {/if}
    {#if task.provider}
      <span class="meta-badge meta-provider"><span class="meta-k">{t('meta.provider')}</span><span class="meta-v">{task.provider}</span></span>
    {/if}
    {#if task.executor}
      <span class="meta-badge meta-executor"><span class="meta-k">{t('meta.executor')}</span><span class="meta-v">{task.executor}</span></span>
    {/if}
    {#if task.task_type}
      <span class="meta-badge meta-type"><span class="meta-k">{t('meta.type')}</span><span class="meta-v">{task.task_type}</span></span>
    {/if}
  </div>

  {#if task.error}
    <div class="task-error">
      <AlertCircleIcon size="13" strokeWidth="2" />
      {task.error}
    </div>
  {/if}

  {#if task.a2a_dispatched && task.a2a_assignments?.length}
    <RoleStrip assignments={task.a2a_assignments} />
  {/if}

  {#if task._live && task._live_progress}
    <div class="live-progress">
      Live · {task._live_progress.done_roles}/{task._live_progress.total_roles}
      {#if task._live_progress.current_role}
        · {task._live_progress.current_role}
      {/if}
    </div>
  {/if}
</div>

<style>
  .inspector-header {
    padding: 10px 16px;
    border-bottom: 1px solid var(--border-default);
    flex-shrink: 0;
  }

  .header-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 5px;
  }

  .task-title {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }

  .task-id {
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--text-muted);
  }

  .task-time {
    font-size: 10px;
    color: var(--text-muted);
    flex-shrink: 0;
  }

  .task-workflow {
    font-size: 12px;
    font-weight: 500;
    color: var(--text-primary);
    background: var(--bg-inset);
    border: 1px solid var(--border-muted);
    border-radius: var(--radius-sm);
    padding: 1px 6px;
  }

  .task-status {
    font-size: 11px;
    font-weight: 500;
    border-radius: var(--radius-sm);
    padding: 1px 6px;
  }
  .status-completed { background: color-mix(in srgb, var(--accent-green) 15%, transparent); color: var(--accent-green); }
  .status-partial { background: color-mix(in srgb, var(--accent-amber, #d4a017) 15%, transparent); color: var(--accent-amber, #d4a017); }
  .status-failed, .status-error { background: color-mix(in srgb, var(--accent-red) 15%, transparent); color: var(--accent-red); }
  .status-running { background: color-mix(in srgb, var(--running-fg) 15%, transparent); color: var(--running-fg); }

  .meta-strip {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
  }

  .meta-badge {
    display: flex;
    align-items: center;
    font-size: 10px;
    border-radius: var(--radius-sm);
    overflow: hidden;
    border: 1px solid;
  }

  .meta-k {
    padding: 1px 5px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    font-size: 9px;
  }

  .meta-v {
    padding: 1px 5px;
    font-weight: 500;
  }

  .meta-agent {
    border-color: color-mix(in srgb, var(--accent-blue) 25%, transparent);
  }
  .meta-agent .meta-k {
    background: color-mix(in srgb, var(--accent-blue) 15%, transparent);
    color: var(--accent-blue);
  }
  .meta-agent .meta-v {
    background: var(--bg-surface);
    color: var(--text-primary);
  }

  .meta-model {
    border-color: color-mix(in srgb, var(--accent-purple) 25%, transparent);
  }
  .meta-model .meta-k {
    background: color-mix(in srgb, var(--accent-purple) 15%, transparent);
    color: var(--accent-purple);
  }
  .meta-model .meta-v {
    background: var(--bg-surface);
    color: var(--text-primary);
  }

  .meta-provider {
    border-color: color-mix(in srgb, var(--accent-sky) 25%, transparent);
  }
  .meta-provider .meta-k {
    background: color-mix(in srgb, var(--accent-sky) 15%, transparent);
    color: var(--accent-sky);
  }
  .meta-provider .meta-v {
    background: var(--bg-surface);
    color: var(--text-primary);
  }

  .meta-executor {
    border-color: color-mix(in srgb, var(--accent-teal) 25%, transparent);
  }
  .meta-executor .meta-k {
    background: color-mix(in srgb, var(--accent-teal) 15%, transparent);
    color: var(--accent-teal);
  }
  .meta-executor .meta-v {
    background: var(--bg-surface);
    color: var(--text-primary);
  }

  .meta-type {
    border-color: color-mix(in srgb, var(--accent-amber) 25%, transparent);
  }
  .meta-type .meta-k {
    background: color-mix(in srgb, var(--accent-amber) 15%, transparent);
    color: var(--accent-amber);
  }
  .meta-type .meta-v {
    background: var(--bg-surface);
    color: var(--text-primary);
  }

  .task-error {
    margin-top: 6px;
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 11px;
    color: var(--accent-red);
    background: color-mix(in srgb, var(--accent-red) 10%, transparent);
    border-radius: var(--radius-sm);
    padding: 4px 8px;
  }

  .live-progress {
    margin-top: 6px;
    font-size: 11px;
    font-weight: 500;
    color: var(--running-fg, var(--accent-amber));
    background: color-mix(in srgb, var(--running-fg, var(--accent-amber)) 10%, transparent);
    border-radius: var(--radius-sm);
    padding: 4px 8px;
  }
</style>
