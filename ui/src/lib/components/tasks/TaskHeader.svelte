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
    border-bottom: 2px solid color-mix(in srgb, var(--voly-orange) 40%, var(--border-default));
    background: color-mix(in srgb, var(--voly-paper) 5%, var(--bg-surface));
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
    color: var(--voly-orange);
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
    border: 1.5px solid var(--voly-orange);
    border-radius: 0;
    padding: 1px 6px;
  }

  .task-status {
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    border: 1.5px solid;
    border-radius: 0;
    padding: 1px 6px;
  }
  .status-completed { background: var(--accent-green); border-color: var(--accent-green); color: var(--accent-green-foreground, #07111f); }
  .status-partial { background: var(--accent-amber, #d4a017); border-color: var(--accent-amber, #d4a017); color: var(--accent-amber-foreground, #07111f); }
  .status-failed, .status-error { background: var(--accent-red); border-color: var(--accent-red); color: var(--accent-red-foreground, #fff); }
  .status-running { background: var(--running-fg); border-color: var(--running-fg); color: var(--bg-primary); }

  .meta-strip {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
  }

  .meta-badge {
    display: flex;
    align-items: center;
    font-size: 10px;
    border-radius: 0;
    overflow: hidden;
    border: 1.5px solid;
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
    border-color: var(--accent-blue);
  }
  .meta-agent .meta-k {
    background: var(--accent-blue);
    color: var(--accent-blue-foreground, #fff);
  }
  .meta-agent .meta-v {
    background: var(--bg-surface);
    color: var(--text-primary);
  }

  .meta-model {
    border-color: var(--accent-purple);
  }
  .meta-model .meta-k {
    background: var(--accent-purple);
    color: var(--accent-purple-foreground, #fff);
  }
  .meta-model .meta-v {
    background: var(--bg-surface);
    color: var(--text-primary);
  }

  .meta-provider {
    border-color: var(--accent-sky);
  }
  .meta-provider .meta-k {
    background: var(--accent-sky);
    color: var(--accent-sky-foreground, #07111f);
  }
  .meta-provider .meta-v {
    background: var(--bg-surface);
    color: var(--text-primary);
  }

  .meta-executor {
    border-color: var(--accent-teal);
  }
  .meta-executor .meta-k {
    background: var(--accent-teal);
    color: var(--accent-teal-foreground, #07111f);
  }
  .meta-executor .meta-v {
    background: var(--bg-surface);
    color: var(--text-primary);
  }

  .meta-type {
    border-color: var(--accent-amber);
  }
  .meta-type .meta-k {
    background: var(--accent-amber);
    color: var(--accent-amber-foreground, #07111f);
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
    border-radius: 0;
    border-left: 3px solid var(--accent-red);
    padding: 4px 8px;
  }

  .live-progress {
    margin-top: 6px;
    font-size: 11px;
    font-weight: 500;
    color: var(--running-fg, var(--accent-amber));
    background: color-mix(in srgb, var(--running-fg, var(--accent-amber)) 10%, transparent);
    border-radius: 0;
    border-left: 3px solid var(--running-fg, var(--accent-amber));
    padding: 4px 8px;
  }
</style>
