<script>
  let { width = '100%', height = '14px', radius = 'var(--radius-sm)', lines = 1, gap = '8px' } = $props()
</script>

<div class="skeleton-wrap" style:gap>
  {#each Array(lines) as _}
    <div class="skeleton" style:width style:height style:border-radius={radius}></div>
  {/each}
</div>

<style>
  .skeleton-wrap {
    display: flex;
    flex-direction: column;
  }

  .skeleton {
    background: var(--bg-inset);
    animation: shimmer 1.5s ease-in-out infinite;
  }

  @keyframes shimmer {
    0%   { opacity: 0.5; }
    50%  { opacity: 0.8; }
    100% { opacity: 0.5; }
  }
</style>
