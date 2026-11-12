<script lang="ts">
  import type { LabNode } from './types';
  let { kind }: { kind: LabNode['kind'] } = $props();
</script>

<g
  fill="none"
  stroke="currentColor"
  stroke-width="1.6"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  {#if kind === 'person'}
    <rect x="2" y="3" width="20" height="14" rx="2.5" /><path
      d="M9 21h6m-3-4v4"
    />
  {:else if kind === 'tor'}
    <path
      d="M12 2c.4 4.6 7.5 7.5 7.5 13a7.5 7.5 0 0 1-15 0C4.5 10 11.7 6.6 12 2Z"
    /><path d="M12 7c0 3.1 4 5.2 4 8.7a4 4 0 0 1-8 0C8 13.2 10.7 10.5 12 7Z" />
  {:else if kind === 'shadowsocks'}
    <path d="M2 10 22 3l-6 18-4-7-10-4Zm10 4L22 3" />
  {:else if kind === 'direct'}
    <path d="M8 7h8v5a4 4 0 0 1-8 0V7Zm2 0V3m4 4V3m-2 13v5h8" />
  {:else if kind === 'provider'}
    <path d="M3 8h18l-2 12H5L3 8Zm3-3h12M8 12h8m-7 4h6" /><circle
      cx="17.5"
      cy="17"
      r=".7"
      fill="currentColor"
      stroke="none"
    />
  {:else if kind === 'mix'}
    <rect x="5" y="5" width="14" height="14" rx="3" /><rect
      x="9"
      y="9"
      width="6"
      height="6"
      rx="1.1"
    /><path
      d="M8 2v3m4-3v3m4-3v3M8 19v3m4-3v3m4-3v3M2 8h3m-3 4h3m-3 4h3m14-8h3m-3 4h3m-3 4h3"
    />
  {:else if kind === 'dht'}
    <path d="m12 5-7 12m7-12 7 12M6 18h12" /><circle
      cx="12"
      cy="4.5"
      r="2.7"
      fill="white"
    /><circle cx="4.5" cy="18" r="2.7" fill="white" /><circle
      cx="19.5"
      cy="18"
      r="2.7"
      fill="white"
    />
  {:else}
    <ellipse cx="12" cy="5.5" rx="8.2" ry="3.2" /><path
      d="M3.8 5.5V18c0 4.3 16.4 4.3 16.4 0V5.5M3.8 12c0 4.3 16.4 4.3 16.4 0"
    />
  {/if}
</g>
