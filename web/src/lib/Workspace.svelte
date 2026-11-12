<script lang="ts">
  import { onDestroy, untrack } from 'svelte';
  import type { LabClient } from './api';
  import type { Snapshot, LabEvent, NodeDetails } from './types';
  import NetworkGraph from './NetworkGraph.svelte';
  import Inspector from './Inspector.svelte';

  let {
    lab,
    events,
    client,
    connected,
  }: {
    lab: Snapshot;
    events: LabEvent[];
    client: LabClient;
    connected: boolean;
  } = $props();
  let selectedNode = $state('');
  let selectedPath = $state('');
  let details = $state<NodeDetails | null>(null);
  let error = $state('');
  let revision = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let busy = false;
  let again = false;
  let disposed = false;

  function refresh(immediate = false) {
    if (disposed || !connected || !selectedNode) return;
    if (busy) {
      again = true;
      return;
    }
    if (immediate) clearTimeout(timer);
    else if (timer) return;
    timer = setTimeout(
      async () => {
        timer = undefined;
        const id = selectedNode,
          version = revision;
        busy = true;
        try {
          const result = await client.inspect(id);
          if (version === revision && !disposed) {
            details = result;
            error = '';
          }
        } catch (e) {
          if (version === revision && !disposed)
            error = e instanceof Error ? e.message : String(e);
        } finally {
          busy = false;
          if (again && !disposed) {
            again = false;
            refresh();
          }
        }
      },
      immediate ? 0 : 220,
    );
  }
  function chooseNode(id: string) {
    selectedNode = id;
    selectedPath = '';
    details = null;
    error = '';
    revision++;
    refresh(true);
  }
  function choosePath(id: string) {
    selectedPath = id;
    selectedNode = '';
    details = null;
    error = '';
    revision++;
    clearTimeout(timer);
    timer = undefined;
  }
  function choosePeer(id: string, pathId: string) {
    chooseNode(id);
    selectedPath = pathId;
  }
  $effect(() => {
    const seq = lab.sequence;
    const online = connected;
    if (online && seq >= 0) untrack(() => refresh());
  });
  onDestroy(() => {
    disposed = true;
    clearTimeout(timer);
  });
</script>

<NetworkGraph
  {lab}
  {events}
  {selectedNode}
  {selectedPath}
  {details}
  onNode={chooseNode}
  onPath={choosePath}
/>
<div class="inspector-tools">
  <label
    >Inspect node
    <select
      value={selectedNode}
      onchange={(e) => chooseNode(e.currentTarget.value)}
      ><option value="">Select a node</option>
      {#each lab.topology.nodes as n (n.id)}<option value={n.id}
          >{n.label} · {n.id}</option
        >{/each}
    </select>
  </label>
  <label
    >Inspect path
    <select
      value={selectedPath}
      onchange={(e) => choosePath(e.currentTarget.value)}
      ><option value="">Select a path</option>
      {#each lab.topology.paths as p (p.id)}<option value={p.id}
          >{p.source_id} ↔ {p.target_id}</option
        >{/each}
    </select>
  </label>
</div>
{#if error}<p role="alert" class="error">{error}</p>{/if}
<Inspector
  {lab}
  {details}
  {selectedNode}
  {selectedPath}
  {events}
  onPeer={choosePeer}
  onNode={chooseNode}
  onPath={choosePath}
/>

<style>
  .inspector-tools {
    display: flex;
    flex-wrap: wrap;
    gap: 12px 18px;
    background: var(--soft);
    border: 1px solid var(--border);
    border-radius: 8px;
    margin: 14px 0;
    padding: 12px 16px;
  }
  label {
    display: flex;
    gap: 10px;
    align-items: center;
    color: var(--muted);
    font-size: 0.79rem;
    font-weight: 600;
  }
  select {
    font-family: var(--mono);
    font-weight: 400;
    font-size: 0.77rem;
    max-width: 15rem;
  }
</style>
