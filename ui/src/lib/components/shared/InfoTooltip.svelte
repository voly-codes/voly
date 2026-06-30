<script>
  let { text, position = 'top', maxWidth = '220px' } = $props()

  let anchor = $state(null)
  let show = $state(false)
  let x = $state(0)
  let y = $state(0)

  function enter() {
    if (!anchor || !text) return
    const r = anchor.getBoundingClientRect()
    if (position === 'bottom') {
      x = r.left + r.width / 2
      y = r.bottom + 7
    } else {
      x = r.left + r.width / 2
      y = r.top - 7
    }
    show = true
  }

  function leave() { show = false }
</script>

<span
  class="tip-anchor"
  bind:this={anchor}
  onmouseenter={enter}
  onmouseleave={leave}
  role="img"
  aria-label={text}
>
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
       stroke-linecap="round" stroke-linejoin="round" width="11" height="11">
    <circle cx="12" cy="12" r="10"/>
    <path d="M12 16v-4"/>
    <circle cx="12" cy="8" r="0.8" fill="currentColor" stroke="none"/>
  </svg>
</span>

{#if show && text}
  <div
    class="tip-box"
    class:tip-bottom={position === 'bottom'}
    style:left="{x}px"
    style:top="{y}px"
    style:max-width={maxWidth}
  >
    {text}
  </div>
{/if}

<style>
  .tip-anchor {
    display: inline-flex;
    align-items: center;
    cursor: default;
    color: var(--text-muted);
    flex-shrink: 0;
    vertical-align: middle;
  }
  .tip-anchor:hover { color: var(--text-secondary); }

  .tip-box {
    position: fixed;
    transform: translateX(-50%) translateY(-100%);
    background: var(--bg-surface, #1e1e1e);
    border: 1px solid var(--border-default, #333);
    border-radius: 4px;
    padding: 6px 9px;
    font-size: 11px;
    font-weight: 400;
    color: var(--text-secondary, #ccc);
    z-index: 99999;
    box-shadow: 0 4px 16px rgba(0,0,0,0.3);
    pointer-events: none;
    line-height: 1.5;
    white-space: normal;
    text-align: left;
    min-width: 130px;
  }

  .tip-bottom {
    transform: translateX(-50%) translateY(0%);
  }
</style>
