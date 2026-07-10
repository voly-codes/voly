<script>
  import { onMount } from 'svelte'

  let { open = $bindable(false), title = '', width = '420px' } = $props()

  function onKey(e) {
    if (e.key === 'Escape') open = false
  }

  onMount(() => {
    if (open) {
      const focusable = document.querySelector('.modal-panel button, .modal-panel input')
      if (focusable) focusable.focus()
    }
  })
</script>

<svelte:window onkeydown={onKey} />

{#if open}
  <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
  <div class="modal-overlay" onclick={() => open = false} role="dialog" aria-modal="true">
    <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
    <div class="modal-panel" style:width onclick={(e) => e.stopPropagation()}>
      {#if title}
        <div class="modal-header">
          <span class="modal-title">{title}</span>
          <button class="modal-close" onclick={() => open = false} aria-label="Close">✕</button>
        </div>
      {/if}
      <div class="modal-body">
        <slot />
      </div>
      {#if $$slots.footer}
        <div class="modal-footer">
          <slot name="footer" />
        </div>
      {/if}
    </div>
  </div>
{/if}

<style>
  .modal-footer {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 8px;
    padding: 10px 16px;
    border-top: 1px solid var(--border-default);
  }

  @keyframes fade-in {
    from { opacity: 0; }
    to   { opacity: 1; }
  }

  .modal-overlay {
    animation: fade-in 0.15s ease;
  }

  .modal-panel {
    animation: scale-in 0.15s ease;
  }

  @keyframes scale-in {
    from { transform: scale(0.96); opacity: 0; }
    to   { transform: scale(1); opacity: 1; }
  }
</style>
