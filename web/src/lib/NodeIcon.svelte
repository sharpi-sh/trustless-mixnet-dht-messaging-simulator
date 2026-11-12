<script lang="ts">
  import { avatarUrl } from './avatars';
  import GraphGlyph from './GraphGlyph.svelte';
  import type { LabNode } from './types';

  let { node, size = 24 }: { node: LabNode; size?: number } = $props();
</script>

{#if node.kind === 'person'}
  <img src={avatarUrl(node.id)} alt="" width={size} height={size} />
{:else}
  <svg
    viewBox="0 0 24 24"
    aria-hidden="true"
    style:width={size + 'px'}
    style:height={size + 'px'}
  >
    <GraphGlyph kind={node.kind} />
  </svg>
{/if}

<style>
  img,
  svg {
    display: block;
    flex: none;
  }
  img {
    border-radius: 50%;
    object-fit: cover;
  }
</style>
