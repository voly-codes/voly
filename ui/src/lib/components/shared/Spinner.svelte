<script>
  let { size = 20, strokeWidth = 2 } = $props()
</script>

<svg class="spinner" width={size} height={size} viewBox="0 0 24 24" fill="none" style:width="{size}px" style:height="{size}px">
  <circle cx="12" cy="12" r="10" stroke="var(--border-default)" stroke-width={strokeWidth} />
  <path
    d="M12 2a10 10 0 0 1 10 10"
    stroke="var(--accent-blue)"
    stroke-width={strokeWidth}
    stroke-linecap="round"
  />
</svg>

<style>
  .spinner {
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }
</style>
