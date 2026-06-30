<script>
  let { report } = $props()
</script>

{#if report}
  <div class="report-block">
    {#if report.summary}
      <div class="report-summary">{report.summary}</div>
    {/if}

    {#if report.files_created?.length || report.files_changed?.length || report.files_deleted?.length}
      <div class="report-files">
        {#each report.files_created ?? [] as f}
          <div class="rf-row rf-created"><span class="rf-icon">+</span><span class="rf-path">{f}</span></div>
        {/each}
        {#each report.files_changed ?? [] as f}
          <div class="rf-row rf-changed"><span class="rf-icon">~</span><span class="rf-path">{f}</span></div>
        {/each}
        {#each report.files_deleted ?? [] as f}
          <div class="rf-row rf-deleted"><span class="rf-icon">−</span><span class="rf-path">{f}</span></div>
        {/each}
      </div>
    {/if}

    {#if report.actions?.length}
      <ul class="report-actions">
        {#each report.actions as action}
          <li>{action}</li>
        {/each}
      </ul>
    {/if}
  </div>
{/if}

<style>
  .report-block {
    padding: 10px 14px 10px;
    border-bottom: 1px solid var(--border-default);
    display: flex;
    flex-direction: column;
    gap: 8px;
    flex-shrink: 0;
  }

  .report-summary {
    font-size: 11.5px;
    color: var(--text-primary);
    line-height: 1.55;
    white-space: pre-wrap;
    word-break: break-word;
  }

  .report-files {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .rf-row {
    display: flex;
    align-items: baseline;
    gap: 6px;
    font-size: 10.5px;
    font-family: var(--font-mono);
  }

  .rf-icon {
    width: 10px;
    flex-shrink: 0;
    font-weight: 700;
    text-align: center;
  }

  .rf-path {
    color: var(--text-secondary);
    word-break: break-all;
  }

  .rf-created .rf-icon { color: var(--accent-green); }
  .rf-changed .rf-icon { color: var(--accent-amber); }
  .rf-deleted .rf-icon { color: var(--accent-red); }

  .report-actions {
    margin: 0;
    padding: 0 0 0 14px;
    display: flex;
    flex-direction: column;
    gap: 3px;
  }

  .report-actions li {
    font-size: 11px;
    color: var(--text-secondary);
    line-height: 1.4;
  }
</style>
