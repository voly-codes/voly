<script>
  import { CheckCircle2Icon, AlertCircleIcon, TriangleAlertIcon, MessageSquareTextIcon, XIcon } from '../../icons.js'
  import { toast } from '../../stores/toastStore.svelte'

  const iconMap = {
    success: CheckCircle2Icon,
    error: AlertCircleIcon,
    warning: TriangleAlertIcon,
    info: MessageSquareTextIcon,
  }
</script>

{#if toast.all.length > 0}
  <div class="toast-container">
    {#each toast.all as t (t.id)}
      {@const Icon = iconMap[t.type]}
      <div class="toast toast-{t.type}">
        <Icon size="14" strokeWidth="2" />
        <span class="toast-msg">{t.message}</span>
        <button class="toast-close" onclick={() => toast.dismiss(t.id)} aria-label="Закрыть">
          <XIcon size="12" strokeWidth="2" />
        </button>
      </div>
    {/each}
  </div>
{/if}

<style>
  .toast-container {
    position: fixed;
    bottom: 16px;
    right: 16px;
    z-index: 200;
    display: flex;
    flex-direction: column;
    gap: 6px;
    max-width: 360px;
    pointer-events: none;
  }

  .toast {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 10px;
    font-size: 12px;
    border-radius: var(--radius-md);
    border: 1px solid;
    box-shadow: var(--shadow-md);
    pointer-events: auto;
    animation: toast-in 0.2s ease;
  }

  .toast-success {
    background: color-mix(in srgb, var(--accent-green) 12%, var(--bg-surface));
    color: var(--accent-green);
    border-color: color-mix(in srgb, var(--accent-green) 30%, transparent);
  }

  .toast-error {
    background: color-mix(in srgb, var(--accent-red) 12%, var(--bg-surface));
    color: var(--accent-red);
    border-color: color-mix(in srgb, var(--accent-red) 30%, transparent);
  }

  .toast-warning {
    background: color-mix(in srgb, var(--accent-amber) 12%, var(--bg-surface));
    color: var(--accent-amber);
    border-color: color-mix(in srgb, var(--accent-amber) 30%, transparent);
  }

  .toast-info {
    background: color-mix(in srgb, var(--accent-blue) 12%, var(--bg-surface));
    color: var(--accent-blue);
    border-color: color-mix(in srgb, var(--accent-blue) 30%, transparent);
  }

  .toast-msg {
    flex: 1;
    line-height: 1.4;
  }

  .toast-close {
    flex-shrink: 0;
    width: 20px;
    height: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--radius-sm);
    opacity: 0.7;
  }

  .toast-close:hover {
    opacity: 1;
    background: color-mix(in srgb, currentColor 12%, transparent);
  }

  @keyframes toast-in {
    from { opacity: 0; transform: translateY(8px); }
    to   { opacity: 1; transform: translateY(0); }
  }
</style>
