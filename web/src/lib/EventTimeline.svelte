<script lang="ts">
  import type { Snapshot, LabEvent, LabNode } from './types';
  import {
    categories,
    makeTimelineIndex,
    eventSummary,
    type Category,
  } from './timeline';
  import { time } from './inspector';
  let {
    lab,
    events,
    onNode,
    onPath,
    onRoute,
  }: {
    lab: Snapshot;
    events: LabEvent[];
    onNode: (id: string) => void;
    onPath: (id: string) => void;
    onRoute: (e: LabEvent) => void;
  } = $props();
  let category = $state<Category>('All events'),
    node = $state(''),
    message = $state(''),
    query = $state('');
  let anchor = $state<number | null>(null),
    selected = $state<LabEvent | null>(null);
  let kindMap = $derived(
    new Map<string, LabNode['kind']>(
      lab.topology.nodes.map((n) => [n.id, n.kind]),
    ),
  );
  const index = makeTimelineIndex();
  let view = $derived(
    index(events, { category, node, message, query }, kindMap),
  );
  const pageSize = 30;
  let end = $derived(Math.min(view.count, anchor ?? view.count));
  let start = $derived(Math.max(0, end - pageSize));
  let visible = $derived(view.rows.slice(start, end));
  function change() {
    anchor = null;
    selected = null;
  }
</script>

<section class="records" aria-labelledby="events-heading">
  <div class="record-head">
    <h2 id="events-heading">Event timeline</h2>
    <small>{view.count.toLocaleString('en-GB')} matching events</small>
  </div>
  <div class="record-filters" onchange={change}>
    <label
      >Event category<select bind:value={category}
        >{#each categories as c (c)}<option value={c}>{c}</option
          >{/each}</select
      ></label
    >
    <label
      >Timeline node<select bind:value={node}
        ><option value="">All nodes</option
        >{#each lab.topology.nodes as n (n.id)}<option value={n.id}
            >{n.label} · {n.id}</option
          >{/each}</select
      ></label
    >
    <label
      >Timeline message<select bind:value={message}
        ><option value="">All messages</option
        >{#each lab.messages as m (m.id)}<option value={m.id}
            >{m.id} · {m.direction} · {m.conversation_id}</option
          >{/each}</select
      ></label
    >
    <label
      >Search events<input
        bind:value={query}
        oninput={change}
        placeholder="Event, conversation or packet"
      /></label
    >
  </div>
  {#if visible.length}
    <div class="record-scroll">
      <table>
        <thead
          ><tr
            ><th>Sequence</th><th>Logical time</th><th>Event</th><th
              >Source → destination</th
            ><th>Message</th><th>Details</th></tr
          ></thead
        ><tbody>
          {#each visible as e (e.sequence)}<tr
              class:chosen={selected?.sequence === e.sequence}
              ><td>{e.sequence}</td><td>{time(e.simulation_time_ms)}</td><td
                ><button
                  class="record-link"
                  onclick={() =>
                    (selected = selected?.sequence === e.sequence ? null : e)}
                  >{e.event_type}</button
                ></td
              ><td
                >{e.source_id ?? '—'}{e.target_id
                  ? ' → ' + e.target_id
                  : ''}</td
              ><td>{e.message_id ?? '—'}</td><td>{eventSummary(e)}</td></tr
            >{/each}
        </tbody>
      </table>
    </div>
    <div class="record-pages">
      <button disabled={start === 0} onclick={() => (anchor = start)}
        >Earlier</button
      ><small>{start + 1}–{end} of {view.count}</small><button
        disabled={end === view.count}
        onclick={() => (anchor = Math.min(view.count, end + pageSize))}
        >Later</button
      ><button disabled={anchor === null} onclick={() => (anchor = null)}
        >Follow live</button
      >
    </div>
  {:else}<p class="records-empty">No events match the current filters.</p>{/if}
  {#if selected}<div class="event-detail">
      <div class="record-head">
        <h3>{selected.event_type}</h3>
        <button onclick={() => (selected = null)}>Close event</button>
      </div>
      <p>
        Sequence {selected.sequence} · {time(selected.simulation_time_ms)} · {selected.conversation_id ??
          'No conversation'}
      </p>
      <div class="record-actions">
        {#if selected.event_type === 'mixnet_route_constructed'}<button
            onclick={() => onRoute(selected!)}>Show recorded route</button
          >{/if}
        {#if selected.source_id}<button
            onclick={() => onNode(selected!.source_id!)}>Inspect source</button
          >{/if}{#if selected.target_id}<button
            onclick={() => onNode(selected!.target_id!)}
            >Inspect destination</button
          >{/if}{#if typeof selected.payload.path_id === 'string'}<button
            onclick={() => onPath(String(selected!.payload.path_id))}
            >Inspect event path</button
          >{/if}
      </div>
      <pre>{JSON.stringify(selected.payload, null, 2)}</pre>
    </div>{/if}
</section>
