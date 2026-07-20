<script>
  let { diff = null } = $props()

  /** @param {string} section */
  function fileNameFromSection(section) {
    const b = section.match(/^\+\+\+ b\/(.+)$/m)
    if (b) return b[1]
    const bPlain = section.match(/^\+\+\+ (.+)$/m)
    if (bPlain) return bPlain[1].replace(/^b\//, '')
    const a = section.match(/^--- a\/(.+)$/m)
    if (a) return a[1]
    const aPlain = section.match(/^--- (.+)$/m)
    if (aPlain) return aPlain[1].replace(/^a\//, '')
    return 'unknown'
  }

  /** @param {string} raw */
  function parseFiles(raw) {
    const text = raw.trim()
    if (!text) return []
    const parts = text.split(/(?=^--- )/m).filter(p => p.trim())
    return parts.map(section => ({
      name: fileNameFromSection(section),
      lines: section.split('\n'),
      open: true,
    }))
  }

  let files = $derived(parseFiles(diff ?? ''))
  /** @type {Record<number, boolean>} */
  let openFiles = $state({})

  function isOpen(index) {
    return openFiles[index] !== false
  }

  /** @param {number} index */
  function toggleFile(index) {
    openFiles[index] = !isOpen(index)
  }

  /** @param {string} line */
  function lineClass(line) {
    if (line.startsWith('+++') || line.startsWith('---')) return 'file-meta'
    if (line.startsWith('@@')) return 'hunk'
    if (line.startsWith('+')) return 'add'
    if (line.startsWith('-')) return 'del'
    return 'ctx'
  }
</script>

{#if diff?.trim()}
  <div class="diff-preview">
    <div class="diff-header">
      Diff preview (dry run)
      <span class="badge">{files.length} file{files.length === 1 ? '' : 's'}</span>
    </div>

    {#each files as file, i}
      <div class="file-block">
        <button type="button" class="file-head" onclick={() => toggleFile(i)}>
          {isOpen(i) ? '▾' : '▸'} {file.name}
        </button>
        {#if isOpen(i)}
          <pre class="file-body">{#each file.lines as line}<span class={lineClass(line)}>{line}{'\n'}</span>{/each}</pre>
        {/if}
      </div>
    {/each}
  </div>
{/if}

<style>
  .diff-preview {
    margin: 0 14px 8px;
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    background: var(--bg-inset);
    overflow: hidden;
  }

  .diff-header {
    font-size: 11px;
    font-weight: 600;
    color: var(--text-secondary);
    padding: 6px 10px;
    border-bottom: 1px solid var(--border-muted);
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .badge {
    font-size: 9px;
    font-weight: 600;
    padding: 1px 6px;
    border-radius: 999px;
    background: color-mix(in srgb, var(--accent-blue) 12%, transparent);
    color: var(--accent-blue);
  }

  .file-block {
    border-bottom: 1px solid var(--border-muted);
  }
  .file-block:last-child { border-bottom: none; }

  .file-head {
    width: 100%;
    text-align: left;
    font-size: 11px;
    font-family: var(--font-mono);
    color: var(--text-primary);
    padding: 5px 10px;
    background: color-mix(in srgb, var(--bg-surface) 60%, transparent);
  }
  .file-head:hover { background: var(--bg-surface-hover); }

  .file-body {
    max-height: 400px;
    overflow-y: auto;
    margin: 0;
    padding: 6px 10px 8px;
    font-family: var(--font-mono);
    font-size: 10px;
    line-height: 1.45;
    white-space: pre-wrap;
    word-break: break-all;
  }

  .file-body :global(.add) {
    display: block;
    background: #1a3320;
    color: #4ade80;
  }

  .file-body :global(.del) {
    display: block;
    background: #3a1a1a;
    color: #f87171;
  }

  .file-body :global(.hunk) {
    display: block;
    color: #9ca3af;
  }

  .file-body :global(.file-meta) {
    display: block;
    color: var(--text-muted);
  }

  .file-body :global(.ctx) {
    display: block;
    color: var(--text-primary);
  }
</style>
