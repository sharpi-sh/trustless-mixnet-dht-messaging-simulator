<script lang="ts">
  import { untrack } from 'svelte';
  import type {
    Snapshot,
    LabEvent,
    NodeDetails,
    Path,
    DeviceLog,
  } from './types';
  import {
    layoutTopology,
    laneCurve,
    onCurve,
    transitFraction,
    contactIds,
    makeTraceHistory,
    extractRoute,
    transitEndpoints,
  } from './graph-layout';
  import GraphGlyph from './GraphGlyph.svelte';
  let {
    lab,
    events,
    selectedNode,
    selectedPath,
    inspectedRoute = null,
    details,
    onNode,
    onPath,
  }: {
    lab: Snapshot;
    events: LabEvent[];
    selectedNode: string;
    selectedPath: string;
    inspectedRoute?: LabEvent | null;
    details: NodeDetails | null;
    onNode: (id: string) => void;
    onPath: (id: string) => void;
  } = $props();
  let viewport: HTMLDivElement;
  let zoom = $state(1),
    showAll = $state(false),
    width = $state(0);
  let topologyKey = $derived(
    lab.simulation_id +
      ':' +
      lab.epoch +
      ':' +
      lab.topology.nodes.map((n) => n.id + '/' + n.stage_index).join(','),
  );
  // The topology IDs drive placement; traffic, coordinates and selected peers are separate concerns.
  let layout = $derived.by(() => {
    void topologyKey;
    return untrack(() =>
      layoutTopology(lab.topology.nodes, lab.topology.paths),
    );
  });
  let devices = $derived(new Map(lab.devices.map((d) => [d.id, d])));
  let liveNodes = $derived(new Map(lab.topology.nodes.map((n) => [n.id, n])));
  let contacts = $derived(contactIds(details, selectedNode));
  let activeCount = $derived(
    lab.topology.paths.reduce(
      (sum, p) => sum + Object.keys(p.active).length,
      0,
    ),
  );
  const history = makeTraceHistory();
  let traces = $derived(history(lab.simulation_id + ':' + lab.epoch, events));
  let pinned = $derived(extractRoute(inspectedRoute));
  let pinnedLegs = $derived(
    (pinned?.legs ?? []).flatMap((leg, i) => {
      const a = layout.nodes.get(leg.source),
        b = layout.nodes.get(leg.target);
      return a && b
        ? [{ ...leg, order: i, d: laneCurve(a, b, leg.lane).d }]
        : [];
    }),
  );
  let pinnedNodes = $derived(new Set(pinned?.nodes));
  let edges = $derived.by(() =>
    lab.topology.paths
      .flatMap((p) => {
        const left = liveNodes.get(p.source_id)!,
          right = liveNodes.get(p.target_id)!;
        const other =
          selectedNode === left.id
            ? right.id
            : selectedNode === right.id
              ? left.id
              : '';
        const known = !!other && contacts.has(other);
        const active = Object.entries(p.active);
        const planned =
            !pinned && ['running', 'paused'].includes(lab.status)
              ? traces.chosen.get(p.id)
              : undefined,
          observed = traces.seen.get(p.id);
        const recentFailure =
          observed?.failed &&
          lab.simulation_time_ms - observed.at <= lab.config.ack_timeout_ms;
        const important =
          p.blocked ||
          active.length ||
          p.id === selectedPath ||
          known ||
          planned ||
          recentFailure;
        // DHT transports are physical links. Only contacts reported by the selected node are labelled known.
        const substrate =
          left.kind === 'dht' ||
          right.kind === 'dht' ||
          left.kind === 'storage' ||
          right.kind === 'storage';
        if (substrate && !showAll && !important && !other && !p.completed)
          return [];
        if (
          left.kind === 'dht' &&
          right.kind === 'dht' &&
          !showAll &&
          !known &&
          !active.length &&
          !p.completed &&
          !p.blocked &&
          p.id !== selectedPath &&
          !recentFailure
        )
          return [];
        const retryTracks = new Set(
          active
            .filter(([, t]) => traces.retries.has(t.token))
            .map(([, t]) => t.source + '/' + t.lane),
        );
        const directions = active.length
          ? active.map(([, t]) => t)
          : [
              planned ??
                observed ?? {
                  source: p.source_id,
                  target: p.target_id,
                  lane: 'forward' as const,
                },
            ];
        const tracks = new Map(
          directions.map(({ source, target, lane }) => [
            source + '/' + lane,
            {
              source,
              target,
              lane,
              retry: retryTracks.has(source + '/' + lane),
              curve: laneCurve(
                layout.nodes.get(source)!,
                layout.nodes.get(target)!,
                lane,
              ),
            },
          ]),
        );
        const lane = directions[0].lane;
        const unreachable =
          left.adjacent_peers?.[right.id]?.status === 'unresponsive' ||
          right.adjacent_peers?.[left.id]?.status === 'unresponsive';
        const state = p.blocked
          ? 'blocked'
          : active.length
            ? 'active'
            : recentFailure
              ? 'failed'
              : !left.online || !right.online || unreachable
                ? 'unavailable'
                : p.id === selectedPath
                  ? 'selected'
                  : known
                    ? 'known'
                    : planned
                      ? 'planned'
                      : p.completed
                        ? 'completed'
                        : 'configured';
        return [
          {
            p,
            state,
            tracks,
            lane,
            known,
            active,
            overlay: !!important,
            other,
          },
        ];
      })
      .sort((a, b) => Number(a.overlay) - Number(b.overlay)),
  );
  let highlight = $derived(
    lab.topology.paths.find((p) => p.id === selectedPath),
  );
  let transits = $derived(
    edges.flatMap((e) =>
      e.active.map(([id, t]) => ({
        id,
        t,
        retry: traces.retries.has(t.token),
        curve: e.tracks.get(t.source + '/' + t.lane)!.curve,
      })),
    ),
  );
  let endpoints = $derived(
    transitEndpoints(
      transits.map((m) => m.t),
      traces.retries,
    ),
  );
  let visualTime = $state(0),
    frameEpoch = '';
  $effect(() => {
    const now = lab.simulation_time_ms,
      next = lab.next_step_ms,
      status = lab.status,
      pace = lab.step_delay_ms;
    const epoch = lab.simulation_id + ':' + lab.epoch,
      hasTraffic = transits.length > 0;
    let start = now;
    if (frameEpoch === epoch)
      start = Math.max(
        now,
        Math.min(
          next ?? now,
          untrack(() => visualTime),
        ),
      );
    frameEpoch = epoch;
    visualTime = start;
    if (status !== 'running' || next === null || next <= start || !hasTraffic)
      return;
    const began = performance.now();
    let frame = 0;
    function draw(ts: number) {
      const t = Math.min(1, (ts - began) / Math.max(1, pace));
      visualTime = start + (next! - start) * t;
      if (t < 1) frame = requestAnimationFrame(draw);
    }
    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  });
  let drag: { x: number; y: number; left: number; top: number } | undefined;
  function down(e: PointerEvent) {
    if (e.button !== 0 && e.button !== 1) return;
    if (
      e.button === 0 &&
      (e.target as Element).closest('[role=button],.device-log')
    )
      return;
    drag = {
      x: e.clientX,
      y: e.clientY,
      left: viewport.scrollLeft,
      top: viewport.scrollTop,
    };
    viewport.setPointerCapture(e.pointerId);
  }
  function move(e: PointerEvent) {
    if (drag) {
      viewport.scrollLeft = drag.left + drag.x - e.clientX;
      viewport.scrollTop = drag.top + drag.y - e.clientY;
    }
  }
  function zoomBy(f: number) {
    zoom = Math.max(0.2, Math.min(2, Math.round(zoom * f * 100) / 100));
  }
  function fit() {
    zoom = Math.max(0.18, Math.min(1, (width - 3) / layout.width));
    viewport.scrollTo(0, 0);
  }
  function handleKey(e: KeyboardEvent, run: () => void) {
    const arrows: Record<string, [number, number]> = {
      ArrowLeft: [-80, 0],
      ArrowRight: [80, 0],
      ArrowUp: [0, -80],
      ArrowDown: [0, 80],
    };
    if (arrows[e.key]) {
      e.preventDefault();
      viewport.scrollBy(...arrows[e.key]);
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      run();
    }
  }
  function stamp(ms: number) {
    const s = Math.floor(ms / 1000);
    return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
  }
  function logLabel(log: DeviceLog) {
    if (log.state === 'staged') return 'DRAFT';
    if (log.state === 'replied') return 'REPLY';
    if (log.state === 'sent') return 'SEND';
    if (log.state === 'received') return 'RECV';
    return log.state.toUpperCase();
  }
  function caption(p: Path) {
    return p.transport_label + ' · ' + p.base_transit_delay_ms + ' ms';
  }
</script>

<section class="network-panel" aria-labelledby="topology-heading">
  <div class="graph-head">
    <div>
      <h2 id="topology-heading">Network topology</h2>
      <p>
        {lab.topology.nodes.length} nodes <span>·</span>
        {lab.topology.paths.length} configured paths <span>·</span>
        {activeCount} in transit
      </p>
    </div>
    <div class="tools">
      <label
        ><input type="checkbox" bind:checked={showAll} /> All transports</label
      >
      <div class="zoom">
        <button
          aria-label="Zoom out"
          title="Zoom out"
          onclick={() => zoomBy(1 / 1.2)}>−</button
        >
        <button
          class="number"
          aria-label="Actual size"
          title="Actual size"
          onclick={() => (zoom = 1)}>{Math.round(zoom * 100)}%</button
        >
        <button aria-label="Zoom in" title="Zoom in" onclick={() => zoomBy(1.2)}
          >+</button
        >
        <button
          class="fit"
          aria-label="Fit graph"
          title="Fit graph"
          onclick={fit}
          ><svg width="15" height="15" viewBox="0 0 16 16" aria-hidden="true"
            ><path
              d="M2 6V2h4m4 0h4v4m0 4v4h-4m-4 0H2v-4"
              fill="none"
              stroke="currentColor"
              stroke-width="1.5"
            /></svg
          ></button
        >
      </div>
    </div>
  </div>
  <div
    class="graph-viewport"
    bind:this={viewport}
    bind:clientWidth={width}
    onpointerdown={down}
    onpointermove={move}
    onpointerup={() => (drag = undefined)}
    onpointercancel={() => (drag = undefined)}
    role="region"
    aria-label="Pan network diagram"
  >
    <svg
      class="world"
      role="group"
      aria-label="Network topology"
      width={layout.width * zoom}
      height={layout.height * zoom}
      viewBox={'0 0 ' + layout.width + ' ' + layout.height}
    >
      <defs
        ><pattern
          id="graph-grid"
          width="14"
          height="14"
          patternUnits="userSpaceOnUse"
          ><circle cx="7" cy="7" r=".65" fill="#768983" opacity=".3" /></pattern
        ></defs
      >
      <rect width={layout.width} height={layout.height} fill="#f8faf8" />
      {#each layout.stages as band (band.index)}
        <g class={'band ' + band.kind}
          ><rect
            x={band.x}
            y="14"
            width={band.width}
            height={layout.height - 28}
            rx="8"
          />
          <text x={band.x + band.width / 2} y="36">{band.name}</text></g
        >
      {/each}
      <rect
        x="0"
        y="49"
        width={layout.width}
        height={layout.height - 62}
        fill="url(#graph-grid)"
        pointer-events="none"
      />
      {#each edges as e (e.p.id)}
        <g
          role="button"
          tabindex="0"
          aria-label={e.p.source_id +
            ' to ' +
            e.p.target_id +
            ', ' +
            caption(e.p)}
          aria-pressed={selectedPath === e.p.id}
          data-path-id={e.p.id}
          data-lane={e.lane}
          data-path-state={e.state}
          class={'edge ' + e.state}
          onclick={() => onPath(e.p.id)}
          onkeydown={(ev) => handleKey(ev, () => onPath(e.p.id))}
        >
          <title
            >{e.p.source_id} ↔ {e.p.target_id} · {caption(e.p)} · {e.known
              ? 'known contact'
              : e.state}</title
          >
          {#each e.tracks as [key, track] (key)}
            <path class="hit" d={track.curve.d} />
            <path
              class="stroke"
              class:retry={track.retry}
              d={track.curve.d}
              data-track-source={track.source}
              data-track-lane={track.lane}
            />
          {/each}
        </g>
      {/each}
      {#each pinnedLegs as leg (leg.order)}
        <path
          class="pinned-route"
          class:retry={pinned?.retry}
          d={leg.d}
          data-inspected-path={leg.id}
          data-route-source={leg.source}
          data-route-target={leg.target}
          pointer-events="none"
        />
      {/each}
      {#each lab.topology.nodes as n (n.id)}
        {@const g = layout.nodes.get(n.id)!}
        {@const device = devices.get(n.id)}
        {@const activity = endpoints.get(n.id)}
        {@const busy = Object.keys(n.delayed_packets ?? {}).length > 0}
        <g
          transform={'translate(' + g.x + ' ' + g.y + ')'}
          role="button"
          tabindex="0"
          aria-pressed={selectedNode === n.id}
          aria-label={n.label +
            ', ' +
            n.kind +
            ', ' +
            (n.online ? 'online' : 'offline')}
          data-node-id={n.id}
          data-route-member={pinnedNodes.has(n.id)}
          data-transit-source={activity?.outgoing ?? 0}
          data-transit-target={activity?.incoming ?? 0}
          data-highlighted={selectedNode === n.id}
          class="graph-node"
          class:selected={selectedNode === n.id}
          class:peer={contacts.has(n.id)}
          class:down={!n.online}
          class:busy
          onclick={() => onNode(n.id)}
          onkeydown={(ev) => handleKey(ev, () => onNode(n.id))}
        >
          <title
            >{n.label} · {n.id} · {n.simulated_address} · {n.online
              ? 'online'
              : 'offline'}</title
          >
          {#if pinnedNodes.has(n.id)}
            <rect
              class="route-node"
              class:retry={pinned?.retry}
              x={-g.w / 2 - 3}
              y={-g.h / 2 - 3}
              width={g.w + 6}
              height={g.h + 6}
              rx="9"
              pointer-events="none"
            />
          {/if}
          <rect
            data-card=""
            class="card"
            x={-g.w / 2}
            y={-g.h / 2}
            width={g.w}
            height={g.h}
            rx={device ? 8 : 7}
          />
          {#if device}
            <g
              transform={'translate(' +
                (-g.w / 2 + 9) +
                ' ' +
                (-g.h / 2 + 10) +
                ') scale(.72)'}><GraphGlyph kind={n.kind} /></g
            >
            <text class="device-title" x={-g.w / 2 + 32} y={-g.h / 2 + 22}
              >{device.label}</text
            >
            <text class="device-sub" x={-g.w / 2 + 10} y={-g.h / 2 + 38}
              >{device.role} · polling {device.polling_enabled
                ? 'on'
                : 'off'}</text
            >
            <text class="key" x={-g.w / 2 + 10} y={-g.h / 2 + 52}
              >{device.fingerprint.slice(0, 16)}…</text
            >
            <line
              x1={-g.w / 2}
              x2={g.w / 2}
              y1={-g.h / 2 + 60}
              y2={-g.h / 2 + 60}
              stroke="#e1e7e3"
            />
            <foreignObject
              x={-g.w / 2 + 8}
              y={-g.h / 2 + 65}
              width={g.w - 16}
              height={g.h - 71}
            >
              <div class="device-log" aria-label={device.label + ' device log'}>
                {#each device.logs as log (log.message_id + '/' + log.state + '/' + log.simulation_time_ms)}<div
                    class="logrow"
                  >
                    <b>{logLabel(log)}</b><time
                      title={log.simulation_time_ms + ' ms'}
                      >{stamp(log.simulation_time_ms)}</time
                    ><span>{log.text || log.state}</span>
                  </div>
                {:else}<span class="empty">No messages</span>{/each}
              </div>
            </foreignObject>
          {:else}
            <g transform="translate(-9,-17) scale(.76)"
              ><GraphGlyph kind={n.kind} /></g
            >
            <text class="node-label" text-anchor="middle" y="14"
              >{n.kind === 'tor'
                ? 'Tor'
                : n.kind === 'provider'
                  ? n.label.replace(' provider', '')
                  : n.label}</text
            >
          {/if}
          {#if activity}
            <g
              class="endpoints"
              transform={'translate(0 ' + (g.h / 2 + 1) + ')'}
              pointer-events="none"
            >
              <title
                >{activity.outgoing} outgoing ({activity.outgoingRetries} retries),
                {activity.incoming} incoming ({activity.incomingRetries} retries)</title
              >
              {#if activity.outgoing}
                <g
                  class="outgoing"
                  class:retry={activity.outgoingRetries > 0}
                  transform="translate(-26,0)"
                >
                  <rect width="25" height="12" rx="3" /><text x="12" y="9"
                    >↑{activity.outgoing}</text
                  >
                </g>
              {/if}
              {#if activity.incoming}
                <g
                  class="incoming"
                  class:retry={activity.incomingRetries > 0}
                  transform="translate(1,0)"
                >
                  <rect width="25" height="12" rx="3" /><text x="12" y="9"
                    >↓{activity.incoming}</text
                  >
                </g>
              {/if}
            </g>
          {/if}
          <circle
            class="health"
            cx={g.w / 2 - 6}
            cy={-g.h / 2 + 6}
            r="3"
            fill={!n.online ? '#bd453b' : busy ? '#bd7919' : '#3b855a'}
          />
        </g>
      {/each}
      {#each transits as m (m.id)}
        {@const pos = onCurve(
          m.curve,
          transitFraction(visualTime, m.t.start_ms, m.t.end_ms),
        )}
        <g
          class="marker"
          data-transit-id={m.id}
          data-retry={m.retry}
          data-source={m.t.source}
          data-target={m.t.target}
          data-lane={m.t.lane}
          transform={'translate(' + pos.x + ' ' + pos.y + ')'}
          pointer-events="none"
        >
          <title
            >{m.t.token} · {m.t.source} → {m.t.target} · {m.t.start_ms}–{m.t
              .end_ms} ms</title
          >
          <circle
            r="6.7"
            fill={m.retry ? '#fff0dd' : '#d6f4df'}
            stroke={m.retry ? '#a94d0a' : '#3a8054'}
            stroke-width="1.1"
          /><circle r="2.6" fill={m.retry ? '#ae500a' : '#267246'} />
        </g>
      {/each}
    </svg>
  </div>
  <div class="legend">
    <span><i class="legend-line"></i>Configured</span><span
      ><i class="legend-line selected"></i>Source route</span
    >
    <span><i class="legend-line active"></i>Active / completed</span><span
      ><i class="legend-line held"></i>Held</span
    >
    <span><i class="legend-line failed"></i>Failed / blocked</span>
    <span><i class="legend-line retry"></i>Retry</span>
    <span>↑ Outgoing · ↓ Incoming</span>
    <span class="lane">↗ Forward <span>·</span> ↙ Reply</span>
  </div>
  {#if highlight}<p class="selected-transport">
      {highlight.source_id} ↔ {highlight.target_id} <span>·</span>
      {caption(highlight)} <span>·</span>
      {highlight.blocked ? 'Blocked' : 'Available'}
    </p>{/if}
</section>

<style>
  .network-panel {
    border: 1px solid var(--border, #dce1dc);
    border-radius: 10px;
    background: white;
    overflow: hidden;
    min-width: 0;
  }
  .graph-head,
  .tools,
  .zoom,
  .legend,
  .legend > span {
    display: flex;
    align-items: center;
  }
  .graph-head {
    justify-content: space-between;
    gap: 12px;
    padding: 15px 18px;
    border-bottom: 1px solid #dfe6e1;
  }
  h2 {
    font-size: 18px;
    letter-spacing: -0.035em;
    margin: 0;
    color: #25352c;
  }
  .graph-head p {
    margin: 4px 0 0;
    font: 11px var(--mono, monospace);
    color: #61736a;
  }
  .graph-head p span,
  .selected-transport span {
    margin: 0 4px;
    color: #9aa8a1;
  }
  .tools {
    gap: 14px;
  }
  .tools label {
    font-size: 12px;
    color: #4d6054;
    white-space: nowrap;
    display: flex;
    gap: 5px;
    align-items: center;
  }
  .tools input {
    width: 13px;
    height: 13px;
    accent-color: #355edb;
  }
  .zoom {
    border: 1px solid #d5ded7;
    border-radius: 6px;
    overflow: hidden;
  }
  .zoom button {
    height: 29px;
    min-width: 28px;
    padding: 0 5px;
    border: 0;
    background: white;
    font: 16px var(--mono, monospace);
    color: #3c4d42;
    display: grid;
    place-items: center;
    border-radius: 0;
  }
  .zoom .number {
    font-size: 10px;
    width: 42px;
  }
  .zoom .fit {
    border-left: 1px solid #d5ded7;
  }
  .zoom button:hover {
    background: #edf2ed;
  }
  .graph-viewport {
    position: relative;
    overflow: auto;
    max-height: min(65vh, 620px);
    min-height: 220px;
    overscroll-behavior: contain;
    scrollbar-color: #b9c8bf #edf1ed;
    cursor: grab;
    background: #f8faf8;
    touch-action: pan-x pan-y;
  }
  .graph-viewport:active {
    cursor: grabbing;
  }
  .world {
    display: block;
    max-width: none;
    flex: none;
  }
  .band rect {
    fill: #ecf1ef;
    stroke: #dce5df;
    stroke-width: 0.7;
  }
  .band.person rect {
    fill: #f1f2ed;
  }
  .band.tor rect {
    fill: #f4f1eb;
  }
  .band.mix rect {
    fill: #ebf3ee;
  }
  .band.dht rect {
    fill: #edf1f8;
  }
  .band.storage rect {
    fill: #f1edf5;
  }
  .band text {
    font:
      600 11px system-ui,
      sans-serif;
    fill: #425747;
    text-anchor: middle;
  }
  .band.dht text {
    fill: #425775;
  }
  .band.storage text {
    fill: #5a4a68;
  }
  .edge {
    cursor: pointer;
  }
  .edge path {
    fill: none;
  }
  .edge .hit {
    stroke: transparent;
    stroke-width: 10;
    pointer-events: stroke;
  }
  .edge .stroke {
    stroke: #a6b4ab;
    stroke-width: 1.1;
    stroke-dasharray: 2 3;
    opacity: 0.55;
    pointer-events: none;
  }
  .edge.completed .stroke {
    stroke: #648c72;
    opacity: 0.65;
  }
  .edge.known .stroke {
    stroke: #4c78a1;
    stroke-dasharray: 3 2;
    opacity: 0.9;
  }
  .edge.planned .stroke,
  .edge.selected .stroke {
    stroke: #4f72c0;
    stroke-width: 2;
    stroke-dasharray: none;
    opacity: 0.92;
  }
  .edge.active .stroke {
    stroke: #388653;
    stroke-width: 2.2;
    stroke-dasharray: none;
    opacity: 1;
  }
  .edge.failed .stroke,
  .edge.blocked .stroke {
    stroke: #b9493a;
    stroke-dasharray: 6 3;
    opacity: 0.95;
    stroke-width: 1.8;
  }
  .edge.unavailable .stroke {
    stroke: #b08774;
    stroke-dasharray: 1 5;
  }
  .edge:hover .stroke,
  .edge:focus-visible .stroke,
  .edge[aria-pressed='true'] .stroke {
    stroke-width: 3;
    opacity: 1;
  }
  .pinned-route {
    fill: none;
    stroke: #3e54c0;
    stroke-width: 3;
    stroke-dasharray: 7 4;
  }
  .route-node {
    fill: none;
    stroke: #3e54c0;
    stroke-width: 2;
    stroke-dasharray: 4 2;
  }
  .edge.active .stroke.retry,
  .pinned-route.retry,
  .route-node.retry {
    stroke: #af520f;
  }
  .endpoints text {
    font: 700 9px var(--mono, monospace);
    text-anchor: middle;
    fill: white;
  }
  .endpoints .outgoing rect {
    fill: #246441;
  }
  .endpoints .incoming rect {
    fill: #236b83;
  }
  .endpoints .retry rect {
    fill: #a44b0d;
  }
  .graph-node {
    cursor: pointer;
    color: #52665a;
  }
  .graph-node .card {
    fill: #fff;
    stroke: #bfcdc3;
    stroke-width: 1.1;
  }
  .graph-node.peer .card {
    stroke: #7797b1;
  }
  .graph-node.down .card {
    fill: #fff3f0;
    stroke: #c78278;
    stroke-dasharray: 3 2;
  }
  .graph-node.busy .card {
    stroke: #be8a43;
  }
  .graph-node:hover .card,
  .graph-node:focus-visible .card,
  .graph-node.selected .card {
    stroke: #345fd1;
    stroke-width: 2.4;
  }
  .health {
    stroke: white;
    stroke-width: 1;
  }
  .node-label {
    font:
      600 10px system-ui,
      sans-serif;
    fill: #33483c;
  }
  .device-title {
    font:
      650 14px system-ui,
      sans-serif;
    fill: #283e30;
  }
  .device-sub {
    font:
      10px system-ui,
      sans-serif;
    fill: #56695c;
  }
  .key {
    font: 9px var(--mono, monospace);
    fill: #6b796f;
  }
  .device-log {
    color: #3e5345;
    overflow: auto;
    height: 100%;
    font:
      10px system-ui,
      sans-serif;
    line-height: 1.25;
    cursor: auto;
    scrollbar-width: thin;
    overflow-wrap: anywhere;
  }
  .logrow {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 1px 3px;
    padding: 1px 0 5px;
  }
  .logrow b,
  .logrow time {
    font: 8px var(--mono, monospace);
    color: #5d7162;
  }
  .logrow b {
    font-weight: 700;
    color: #366c4b;
  }
  .logrow span {
    grid-column: 1/-1;
  }
  .empty {
    color: #77847b;
  }
  .legend {
    gap: 15px;
    padding: 10px 17px;
    border-top: 1px solid #e0e7e1;
    flex-wrap: wrap;
  }
  .legend > span {
    gap: 5px;
    font-size: 10px;
    color: #53665a;
  }
  .legend-line {
    width: 16px;
    border-top: 2px dotted #81958a;
  }
  .legend-line.active {
    border-top: 2px solid #388653;
  }
  .legend-line.selected {
    border-top: 2px solid #4f72c0;
  }
  .legend-line.retry {
    border-top: 2px dashed #af520f;
  }
  .legend-line.held {
    border-top: 2px solid #be8a43;
  }
  .legend-line.failed {
    border-top: 2px dashed #b9493a;
  }
  .legend .lane {
    margin-left: auto;
    font: 10px var(--mono, monospace);
    color: #66766c;
  }
  .lane > span {
    margin: 0 3px;
  }
  .selected-transport {
    font: 11px var(--mono, monospace);
    color: #52665a;
    padding: 0 17px 10px;
    margin: 0;
  }
  @media (max-width: 650px) {
    .graph-head {
      flex-wrap: wrap;
      padding: 12px;
    }
    .tools {
      gap: 9px;
    }
    .legend {
      gap: 8px;
      padding: 8px 11px;
    }
    .legend .lane {
      margin-left: 0;
    }
  }
</style>
