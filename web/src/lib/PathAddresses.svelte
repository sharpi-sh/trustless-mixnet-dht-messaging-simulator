<script lang="ts">
  import type { Path, LabNode } from './types';
  import IPObservation from './IPObservation.svelte';
  let { path, nodes }: { path: Path; nodes: LabNode[] } = $props();
  const proxy = $derived(
    nodes.find(
      (n) =>
        n.kind === 'shadowsocks' &&
        (n.id === path.source_id || n.id === path.target_id),
    ),
  );
</script>

<section aria-label="Configured IP visibility">
  <h3>Configured IP visibility</h3>
  <div class="directions">
    {#each [path.source_id, path.target_id] as source (source)}
      {@const hop = path.ip_hops?.[source]}
      {#if hop}
        <IPObservation
          {hop}
          proxyEgress={proxy?.egress_address}
          heading={source + ' → ' + hop.observer}
        />
      {/if}
    {/each}
  </div>
  {#if !path.ip_hops}<p>
      The backend did not report IP visibility for this path.
    </p>{/if}
</section>

<style>
  section {
    margin: 0.65rem 0;
  }
  h3 {
    margin: 0;
    font-size: 0.9rem;
  }
  .directions {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 20rem), 1fr));
    gap: 0.4rem 1.5rem;
  }
  p {
    margin: 0.4rem 0;
    font-size: 0.8rem;
    color: var(--muted);
  }
</style>
