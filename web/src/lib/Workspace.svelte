<script lang="ts">
  import { onDestroy, tick, untrack } from 'svelte';
  import type { LabClient } from './api';
  import type { Snapshot, LabEvent, NodeDetails } from './types';
  import NetworkGraph from './NetworkGraph.svelte';
  import Inspector from './Inspector.svelte';
  import InspectorPicker from './InspectorPicker.svelte';
  import Interventions from './Interventions.svelte';
  import EventTimeline from './EventTimeline.svelte';
  import LineageLedger from './LineageLedger.svelte';

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
  let inspectedRoute = $state<LabEvent | null>(null);
  let inspectorAnchor: HTMLDivElement;
  let graphAnchor: HTMLDivElement;
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
  async function inspectFromHistory(id: string, kind: 'node' | 'path') {
    if (kind === 'node') chooseNode(id);
    else choosePath(id);
    await tick();
    inspectorAnchor.scrollIntoView({ block: 'start' });
  }
  async function inspectRoute(event: LabEvent) {
    inspectedRoute = event;
    await tick();
    graphAnchor.scrollIntoView({ block: 'start' });
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

<div bind:this={graphAnchor}>
  {#if inspectedRoute}<div class="inspector-tools">
      Recorded route · {inspectedRoute.message_id} · {inspectedRoute.payload
        .packet_id}<button onclick={() => (inspectedRoute = null)}
        >Clear recorded route</button
      >
    </div>{/if}
  <NetworkGraph
    {inspectedRoute}
    {lab}
    {events}
    {selectedNode}
    {selectedPath}
    {details}
    onNode={chooseNode}
    onPath={choosePath}
  >
    {#snippet runtimeControls()}
      <Interventions {lab} {selectedNode} {selectedPath} {client} {connected} />
    {/snippet}
  </NetworkGraph>
</div>
<div class="inspection-layout">
  <div class="inspection-column" bind:this={inspectorAnchor}>
    <InspectorPicker
      {lab}
      {selectedNode}
      {selectedPath}
      onNode={chooseNode}
      onPath={choosePath}
    />
    {#if error}<p role="alert" class="error">{error}</p>{/if}
    <div class="information">
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
    </div>
  </div>
  <div class="records-column">
    <EventTimeline
      {lab}
      {events}
      onRoute={inspectRoute}
      onNode={(id) => inspectFromHistory(id, 'node')}
      onPath={(id) => inspectFromHistory(id, 'path')}
    />
    <LineageLedger {lab} onNode={(id) => inspectFromHistory(id, 'node')} />
  </div>
</div>

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
  .inspection-layout {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 16px;
    align-items: start;
    margin-top: 16px;
  }
  .inspection-column,
  .records-column {
    min-width: 0;
    display: grid;
    gap: 12px;
  }
  .records-column :global(.records) {
    min-width: 0;
    margin: 0;
  }
  .information {
    min-width: 0;
    padding: clamp(12px, 1.4vw, 22px);
    background: white;
    border: 1px solid var(--border);
    border-radius: 9px;
  }
  @media (max-width: 850px) {
    .inspection-layout {
      grid-template-columns: minmax(0, 1fr);
    }
  }
</style>
