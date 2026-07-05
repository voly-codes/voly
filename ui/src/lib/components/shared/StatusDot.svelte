<script>
  let { status = 'completed', size = 8 } = $props()

  const map = {
    completed: { color: 'var(--accent-green)', pulse: false },
    running:   { color: 'var(--running-fg)',   pulse: true  },
    failed:    { color: 'var(--accent-red)',    pulse: false },
    error:     { color: 'var(--accent-red)',    pulse: false },
    pending:   { color: 'var(--status-waiting)',pulse: false },
  }

  let { color, pulse } = $derived(map[status] ?? { color: 'var(--text-muted)', pulse: false })
</script>

<span
  class="dot"
  class:pulse
  style="width:{size}px;height:{size}px;background:{color}"
  title={status}
></span>

<style>
  .dot {
    display: inline-block;
    border-radius: 50%;
    flex-shrink: 0;
    vertical-align: middle;
  }
  .pulse {
    animation: status-pulse 1.8s ease-in-out infinite;
  }
  @keyframes status-pulse {
    0%, 100% { opacity: 1; box-shadow: 0 0 0 0 transparent; }
    50%       { opacity: 0.7; box-shadow: 0 0 6px 3px color-mix(in srgb, var(--running-fg) 40%, transparent); }
  }
</style>
