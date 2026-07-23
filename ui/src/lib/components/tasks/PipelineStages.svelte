<script>
  import { CheckCircle2Icon, AlertCircleIcon } from '../../icons.js'

  let { stages = [] } = $props()
</script>

{#each stages as stage, i (stage.id)}
  <div class="stage" class:stage-error={!stage.ok}>
    <div class="stage-connector">
      <div class="stage-icon" class:stage-icon-ok={stage.ok} class:stage-icon-err={!stage.ok}>
        {#if stage.icon}
          {@const Icon = stage.icon}
          <Icon size="13" strokeWidth="2" />
        {/if}
      </div>
      {#if i < stages.length - 1}
        <div class="stage-line"></div>
      {/if}
    </div>

    <div class="stage-body">
      <div class="stage-top">
        <span class="stage-label">{stage.label}</span>
        {#if stage.badge}
          <span class="stage-badge" style:color={stage.badgeColor ?? 'var(--text-muted)'}>
            {stage.badge}
          </span>
        {/if}
        {#if stage.ok}
          <CheckCircle2Icon size="11" strokeWidth="2" class="stage-check" />
        {:else}
          <AlertCircleIcon size="11" strokeWidth="2" class="stage-err-icon" />
        {/if}
      </div>
      <div class="stage-detail">{stage.detail}</div>
      {#if stage.meta}
        <div class="stage-meta">{stage.meta}</div>
      {/if}
      {#if stage.hint}
        <div class="stage-hint">{stage.hint}</div>
      {/if}
    </div>
  </div>
{/each}

<style>
  .stage {
    display: flex;
    gap: 12px;
    min-height: 48px;
  }

  .stage-connector {
    display: flex;
    flex-direction: column;
    align-items: center;
    flex-shrink: 0;
    width: 24px;
  }

  .stage-icon {
    width: 24px;
    height: 24px;
    border-radius: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    background: var(--bg-inset);
    color: var(--text-muted);
    border: 2px solid var(--border-default);
  }

  .stage-icon-ok {
    background: color-mix(in srgb, var(--accent-blue) 10%, transparent);
    color: var(--accent-blue);
    border-color: color-mix(in srgb, var(--accent-blue) 30%, transparent);
  }

  .stage-icon-err {
    background: color-mix(in srgb, var(--accent-red) 10%, transparent);
    color: var(--accent-red);
    border-color: color-mix(in srgb, var(--accent-red) 30%, transparent);
  }

  .stage-line {
    flex: 1;
    width: 2px;
    background: var(--border-default);
    margin: 3px 0;
    min-height: 12px;
  }

  .stage-body {
    flex: 1;
    padding-bottom: 14px;
    padding-top: 2px;
  }

  .stage-top {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 2px;
  }

  .stage-label {
    font-size: 13px;
    font-weight: 600;
    color: var(--text-primary);
  }

  .stage-badge {
    font-size: 10px;
    font-weight: 500;
    font-family: var(--font-mono);
    margin-left: auto;
  }

  :global(.stage-check) { color: var(--accent-green); margin-left: auto; }
  :global(.stage-err-icon) { color: var(--accent-red); margin-left: auto; }

  .stage-detail { font-size: 12px; color: var(--text-secondary); }

  .stage-meta {
    font-size: 10px;
    color: var(--text-muted);
    font-family: var(--font-mono);
    margin-top: 1px;
  }

  .stage-hint {
    font-size: 11px;
    color: var(--text-muted);
    line-height: 1.4;
    margin-top: 3px;
    font-style: italic;
  }
</style>
