<script>
  import { ExternalLinkIcon, ImageIcon } from '../../icons.js'

  let { artifacts = [] } = $props()

  let images = $derived((artifacts ?? []).filter(a => a?.kind === 'pxpipe_image' && a?.url))

  function fmtBytes(n) {
    if (!n) return ''
    if (n < 1024) return `${n} B`
    return `${(n / 1024).toFixed(1)} KB`
  }
</script>

{#if images.length}
  <div class="pxpipe-artifacts">
    <div class="artifacts-head">
      <ImageIcon size="12" strokeWidth="2" />
      <span>pxpipe images</span>
      <span class="artifact-count">{images.length}</span>
    </div>
    <div class="artifact-grid">
      {#each images as img}
        <a class="artifact-item" href={img.url} target="_blank" rel="noreferrer" title={img.name}>
          <img src={img.url} alt={img.name ?? 'pxpipe rendered prompt'} loading="lazy" />
          <span class="artifact-meta">
            <span>{fmtBytes(img.bytes)}</span>
            <ExternalLinkIcon size="11" strokeWidth="2" />
          </span>
        </a>
      {/each}
    </div>
  </div>
{/if}

<style>
  .pxpipe-artifacts {
    border-bottom: 1px solid var(--border-muted);
    padding: 8px 10px;
  }

  .artifacts-head {
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 9px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-muted);
    margin-bottom: 7px;
  }

  .artifact-count {
    font-size: 9px;
    color: var(--text-secondary);
    background: var(--bg-inset);
    border: 1px solid var(--border-muted);
    border-radius: var(--radius-sm);
    padding: 0 5px;
  }

  .artifact-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(104px, 1fr));
    gap: 8px;
  }

  .artifact-item {
    position: relative;
    display: block;
    aspect-ratio: 4 / 3;
    overflow: hidden;
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    background: var(--bg-inset);
  }

  .artifact-item:hover {
    border-color: color-mix(in srgb, var(--accent-blue) 45%, var(--border-default));
  }

  .artifact-item img {
    width: 100%;
    height: 100%;
    object-fit: contain;
    display: block;
  }

  .artifact-meta {
    position: absolute;
    left: 4px;
    right: 4px;
    bottom: 4px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 4px;
    min-height: 18px;
    padding: 1px 5px;
    border-radius: var(--radius-sm);
    background: color-mix(in srgb, var(--bg-surface) 86%, transparent);
    color: var(--text-secondary);
    font-size: 9px;
    font-variant-numeric: tabular-nums;
    backdrop-filter: blur(4px);
  }
</style>
