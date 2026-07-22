<script>
  let { open = $bindable(false), title = '', width = '360px', children } = $props()

  function onKey(e) {
    if (e.key === 'Escape') open = false
  }
</script>

<svelte:window onkeydown={onKey} />

{#if open}
  <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
  <div class="backdrop" onclick={() => open = false}></div>
  <div class="drawer" style:width role="dialog" aria-modal="true">
    <div class="drawer-header">
      <span class="drawer-title">{title}</span>
      <button class="drawer-close" onclick={() => open = false} aria-label="Close">✕</button>
    </div>
    <div class="drawer-body">
      {@render children()}
    </div>
  </div>
{/if}

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    background: var(--overlay-bg);
    z-index: 40;
    animation: fade-in 0.15s ease;
  }

  .drawer {
    position: fixed;
    top: 0;
    right: 0;
    bottom: 0;
    z-index: 50;
    display: flex;
    flex-direction: column;
    background: var(--bg-surface);
    border-left: 3px solid var(--voly-ink);
    box-shadow: -7px 0 0 color-mix(in srgb, var(--voly-orange) 82%, transparent);
    animation: slide-in 0.2s cubic-bezier(0.25, 0.46, 0.45, 0.94);
  }

  .drawer-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 14px;
    height: 40px;
    border-bottom: 3px solid var(--voly-ink);
    background: color-mix(in srgb, var(--voly-orange) 9%, var(--bg-surface));
    flex-shrink: 0;
  }

  .drawer-title {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-primary);
    font-family: var(--font-mono);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  .drawer-close {
    width: 24px;
    height: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 14px;
    color: var(--text-muted);
    border-radius: 0;
    transition: background 0.1s, color 0.1s;
  }
  .drawer-close:hover {
    background: var(--bg-inset);
    color: var(--text-primary);
  }

  .drawer-body {
    flex: 1;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
  }

  @keyframes fade-in {
    from { opacity: 0; }
    to   { opacity: 1; }
  }

  @keyframes slide-in {
    from { transform: translateX(100%); }
    to   { transform: translateX(0); }
  }
</style>
