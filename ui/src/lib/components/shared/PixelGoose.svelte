<script>
  const GOOSE = [
    '..oooo..........',
    '..okoo..........',
    'ooooo...........',
    '...oo...........',
    '...oo...........',
    '...oo...........',
    '...oo...........',
    '...ooooooooo....',
    '..ooooooooooo...',
    '..oooooooooooo..',
    '..ooooooooooooo.',
    '..ooooooooooooo.',
    '..oooooooooooo..',
    '...oooooooooo...',
    '....oooooooo....',
    '.....oo...oo....',
    '.....oo...oo....',
    '.....oo...oo....',
    '....ooo..ooo....',
  ]

  let { size = 24, title = '' } = $props()
  const pixels = GOOSE.flatMap((row, y) => [...row].flatMap((cell, x) => (
    cell === '.' ? [] : [{ x, y, eye: cell === 'k' }]
  )))
</script>

<svg
  class="pixel-goose"
  width={size}
  height={size * 19 / 16}
  viewBox="0 0 16 19"
  role={title ? 'img' : undefined}
  aria-label={title || undefined}
  aria-hidden={title ? undefined : 'true'}
  shape-rendering="crispEdges"
>
  {#each pixels as pixel}
    <rect class:eye={pixel.eye} x={pixel.x} y={pixel.y} width="1" height="1" />
  {/each}
</svg>

<style>
  .pixel-goose { display: block; flex: 0 0 auto; overflow: visible; image-rendering: pixelated; }
  rect { fill: var(--voly-orange); }
  rect.eye { fill: var(--voly-ink); }
</style>
