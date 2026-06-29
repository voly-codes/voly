<script lang="ts">
  import { CheckIcon, CopyIcon } from "../../icons.js";

  interface Props {
    copied: boolean;
    ariaLabel: string;
    copiedAriaLabel: string;
    title: string;
    copiedTitle: string;
    onclick?: (event: MouseEvent) => void | Promise<void>;
    class?: string;
  }

  let {
    copied,
    ariaLabel,
    copiedAriaLabel,
    title,
    copiedTitle,
    onclick,
    class: className = "",
  }: Props = $props();
</script>

<button
  type="button"
  class={`copy-btn ${className}`.trim()}
  aria-label={copied ? copiedAriaLabel : ariaLabel}
  title={copied ? copiedTitle : title}
  {onclick}
>
  {#if copied}
    <CheckIcon size="14" strokeWidth="2.4" aria-hidden="true" />
  {:else}
    <CopyIcon size="14" strokeWidth="2" aria-hidden="true" />
  {/if}
</button>

<style>
  .copy-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 26px;
    height: 26px;
    border: none;
    border-radius: var(--radius-sm, 4px);
    background: transparent;
    color: var(--text-muted);
    cursor: pointer;
    opacity: 0;
    transition: opacity 0.15s, background 0.15s, color 0.15s;
    flex-shrink: 0;
  }

  .copy-btn:focus-visible {
    opacity: 1;
  }

  @media (hover: none) {
    .copy-btn {
      opacity: 1;
    }
  }

  .copy-btn:hover {
    background: var(--bg-surface-hover);
    color: var(--text-secondary);
  }

  .copy-btn:active {
    transform: scale(0.92);
  }
</style>
