<script lang="ts">
  import { untrack } from 'svelte';
  import type { Snapshot, LabEvent, NodeDetails, Path } from './types';
  import {
    layoutTopology,
    laneCurve,
    onCurve,
    transitFraction,
    contactIds,
    makeTraceHistory,
    makeTrackRenderer,
    type MessageLeg,
    extractRoute,
    transitEndpoints,
  } from './graph-layout';
  import { channelNames, isChannel } from './channels';
  import IPObservation from './IPObservation.svelte';
  import PathAddresses from './PathAddresses.svelte';
  import GraphGlyph from './GraphGlyph.svelte';
  import ConversationColumn from './ConversationColumn.svelte';
  import { avatarUrl } from './avatars';
  let {
    lab,
    events,
    selectedNode,
    selectedPath,
    inspectedRoute = null,
    details,
    onNode,
    onPath,
    onLeg,
  }: {
    lab: Snapshot;
    events: LabEvent[];
    selectedNode: string;
    selectedPath: string;
    inspectedRoute?: LabEvent | null;
    details: NodeDetails | null;
    onNode: (id: string) => void;
    onPath: (id: string) => void;
    onLeg?: (leg: MessageLeg) => void;
  } = $props();
  let viewport: HTMLDivElement;
  let panel: HTMLElement;
  let screenButton: HTMLButtonElement;
  let expanded = $state(false),
    autoFit = $state(true);
  function toggleScreen() {
    expanded = !expanded;
    fit();
    if (!expanded) screenButton.focus({ preventScroll: true });
  }
  $effect(() => {
    if (!expanded) return;
    // Keep keyboard navigation in the diagram while it covers the workspace.
    const background: HTMLElement[] = [];
    let branch: HTMLElement | null = panel;
    while (branch && branch !== document.body && branch.parentElement) {
      for (const sibling of branch.parentElement.children) {
        if (
          sibling instanceof HTMLElement &&
          sibling !== branch &&
          !sibling.inert
        ) {
          sibling.inert = true;
          background.push(sibling);
        }
      }
      branch = branch.parentElement;
    }
    return () => {
      for (const sibling of background) sibling.inert = false;
    };
  });
  function screenKey(e: KeyboardEvent) {
    if (expanded && e.key === 'Escape') {
      e.preventDefault();
      toggleScreen();
    }
  }
  let zoom = $state(1),
    showAll = $state(false),
    width = $state(0),
    height = $state(0);
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
    const space = { width, height };
    return untrack(() =>
      layoutTopology(lab.topology.nodes, lab.topology.paths, space),
    );
  });
  let devices = $derived(new Map(lab.devices.map((d) => [d.id, d])));
  let liveNodes = $derived(new Map(lab.topology.nodes.map((n) => [n.id, n])));
  let chatChoice = $state({ sender: '', receiver: '' });
  function chatOwner(role: 'sender' | 'receiver') {
    const selected = devices.get(chatChoice[role]);
    return selected?.role === role
      ? selected
      : lab.devices.find((d) => d.role === role);
  }
  const sender = $derived(chatOwner('sender'));
  const receiver = $derived(chatOwner('receiver'));
  function selectNode(id: string) {
    const participant = devices.get(id);
    if (participant) chatChoice[participant.role] = id;
    onNode(id);
  }
  let contacts = $derived(contactIds(details, selectedNode));
  const history = makeTraceHistory();
  let traces = $derived(history(lab.simulation_id + ':' + lab.epoch, events));
  let pick = $state<{ epoch: string; id: string } | null>(null);
  let epoch = $derived(lab.simulation_id + '/' + lab.epoch);
  let selectedLeg = $derived(
    pick?.epoch === epoch ? traces.legs.get(pick.id) : undefined,
  );
  let pathMap = $derived(
    new Map(lab.topology.paths.map((path) => [path.id, path])),
  );
  const renderTrack = $derived(makeTrackRenderer(layout));
  let messageTracks = $derived.by(() =>
    Array.from(traces.messageTracks.values()).flatMap((track) => {
      if (!pathMap.has(track.pathId)) return [];
      const latest = traces.legs.get(track.legs[track.legs.length - 1])!;
      return renderTrack(track, latest) ?? [];
    }),
  );
  let messageTrackMap = $derived(
    new Map(messageTracks.map((track) => [track.id, track])),
  );
  const trackId = (leg: MessageLeg) =>
    [leg.pathId, leg.lane, leg.source, leg.messageId].join('/');
  let pickedTrack = $derived(
    selectedLeg ? messageTrackMap.get(trackId(selectedLeg)) : undefined,
  );
  function choosePath(id: string) {
    pick = null;
    onPath(id);
  }
  function chooseLeg(leg: MessageLeg) {
    pick = { epoch, id: leg.id };
    onPath(leg.pathId);
    onLeg?.(leg);
  }
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
        const active = Object.entries(p.active).filter(
          ([id, t]) =>
            showAll || traces.legs.has(id) || t.token.startsWith('poll-'),
        );
        const planned =
            showAll && !pinned && ['running', 'paused'].includes(lab.status)
              ? traces.chosen.get(p.id)
              : undefined,
          observed = (showAll ? traces.seen : traces.seenMessages).get(p.id);
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
        if (substrate && !showAll && !important && !other) return [];
        if (
          left.kind === 'dht' &&
          right.kind === 'dht' &&
          !showAll &&
          !important
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
                      : (showAll ? p.completed : observed && !observed.failed)
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
            substrate,
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
    edges
      .flatMap((e) =>
        e.active.map(([id, t]) => {
          const leg = traces.legs.get(id),
            track = leg ? messageTrackMap.get(trackId(leg)) : undefined;
          return {
            id,
            t,
            leg,
            poll: t.token.startsWith('poll-'),
            colour: track?.colour,
            retry: traces.retries.has(t.token),
            curve: track?.curve ?? e.tracks.get(t.source + '/' + t.lane)!.curve,
          };
        }),
      )
      .sort((a, b) => Number(!!a.leg) - Number(!!b.leg)),
  );
  let endpoints = $derived(
    transitEndpoints(
      transits.map((m) => m.t),
      traces.retries,
    ),
  );
  let markerTimes = $state.raw<Record<string, number>>({});
  let frameEpoch = '';
  $effect(() => {
    const now = lab.simulation_time_ms,
      next = lab.next_step_ms,
      pace = lab.step_delay_ms;
    const running = lab.status === 'running';
    const previous = frameEpoch === epoch ? untrack(() => markerTimes) : {};
    frameEpoch = epoch;
    const flights = transits.map(({ id, t, leg }) => {
      const start = Math.max(now, previous[id] ?? t.start_ms);
      // Playback can batch a background action at this exact logical timestamp.
      // A payload has its own reported arrival time, independent of the next action.
      // The moving marker stays inside the link until Python retires the transit.
      const end =
        leg || t.token.startsWith('poll-')
          ? t.end_ms
          : Math.min(t.end_ms, next ?? now);
      return { id, start, end: Math.max(start, end) };
    });
    function positions(fraction: number) {
      return Object.fromEntries(
        flights.map(({ id, start, end }) => [
          id,
          start + (end - start) * fraction,
        ]),
      );
    }
    markerTimes = positions(0);
    if (!running || !flights.some((flight) => flight.end > flight.start))
      return;
    const began = performance.now();
    let frame = 0;
    function draw(ts: number) {
      const fraction = Math.min(1, (ts - began) / Math.max(1, pace));
      markerTimes = positions(fraction);
      if (fraction < 1) frame = requestAnimationFrame(draw);
    }
    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  });
  let drag: { x: number; y: number; left: number; top: number } | undefined;
  function down(e: PointerEvent) {
    if (e.button !== 0 && e.button !== 1) return;
    if (e.button === 0 && (e.target as Element).closest('[role=button]'))
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
    autoFit = false;
    const fitted = Math.min(width / layout.width, height / layout.height);
    zoom = Math.max(
      Math.min(0.2, fitted / 2),
      Math.min(Math.max(2, fitted * 3), zoom * f),
    );
  }
  function fit() {
    autoFit = true;
    viewport.scrollTo(0, 0);
  }
  $effect(() => {
    if (autoFit && width > 0 && height > 0)
      zoom = Math.min(width / layout.width, height / layout.height);
  });
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
  function caption(p: Path) {
    return p.transport_label + ' · ' + p.base_transit_delay_ms + ' ms';
  }
</script>

<svelte:window onkeydown={screenKey} />
<section
  class="network-panel"
  class:expanded
  bind:this={panel}
  aria-labelledby="topology-heading"
>
  <div class="graph-head">
    <div>
      <h2 id="topology-heading">Network topology</h2>
      <p>
        {lab.topology.nodes.length} nodes <span>·</span>
        {lab.topology.paths.length} configured paths <span>·</span>
        {transits.length}
        {showAll ? 'in transit' : 'message and poll transits'}
      </p>
      {#if receiver}
        <p data-poll-owner={receiver.id}>
          {receiver.label} · {receiver.polling_enabled
            ? 'Poll every ' + lab.config.polling_interval_ms + ' ms'
            : 'Polling disabled'}
          {#if traces.pollStarts.has(receiver.id)}
            · Last request {traces.pollStarts.get(receiver.id)} ms
          {/if}
          {#if traces.pollResults.has(receiver.id)}
            · {traces.pollResults.get(receiver.id)}
          {/if}
        </p>
      {/if}
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
          onclick={() => {
            autoFit = false;
            zoom = 1;
          }}>{Math.round(zoom * 100)}%</button
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
      <button
        class="screen-button"
        bind:this={screenButton}
        aria-expanded={expanded}
        onclick={toggleScreen}
        >{expanded ? 'Close full screen' : 'Full screen'}</button
      >
    </div>
  </div>
  <div class="diagram-layout">
    {#key lab.simulation_id + '/' + lab.epoch + '/' + sender?.id}
      <ConversationColumn
        role="sender"
        devices={lab.devices}
        messages={lab.messages}
        selectedId={sender?.id}
        address={liveNodes.get(sender?.id ?? '')?.simulated_address}
      />
    {/key}
    <div
      class="graph-viewport"
      bind:this={viewport}
      bind:clientWidth={width}
      bind:clientHeight={height}
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
            ><circle
              cx="7"
              cy="7"
              r=".65"
              fill="#768983"
              opacity=".3"
            /></pattern
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
            class:substrate={e.substrate}
            class:context={!showAll && !e.known && e.p.id !== selectedPath}
            onclick={() => choosePath(e.p.id)}
            onkeydown={(ev) => handleKey(ev, () => choosePath(e.p.id))}
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
        {#each messageTracks as track (track.id)}
          <g
            class="message-track"
            class:failed={track.latest.status === 'failed'}
            class:chosen={pickedTrack?.id === track.id}
            style:--message-colour={track.colour}
            data-message-id={track.messageId}
            data-message-path={track.pathId}
            data-leg-status={track.latest.status}
            data-source={track.source}
            data-target={track.target}
            data-lane={track.lane}
            role="button"
            tabindex="0"
            aria-label={track.messageId +
              ' · ' +
              track.source +
              ' to ' +
              track.target +
              ' · ' +
              track.legs.length +
              ' transits'}
            onclick={() => chooseLeg(track.latest)}
            onkeydown={(e) => handleKey(e, () => chooseLeg(track.latest))}
          >
            <title
              >{track.messageId} · {track.source} → {track.target} · {track
                .latest.status}</title
            >
            <path class="message-hit" d={track.curve.d} />
            <path class="message-halo" d={track.curve.d} />
            <path class="message-line" d={track.curve.d} />
            {#if track.latest.status !== 'active'}
              <circle
                class="history-dot"
                data-history-leg={track.latest.id}
                cx={track.dot.x}
                cy={track.dot.y}
                r={Math.min(12, 4.4 / zoom)}
              />
            {/if}
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
            aria-pressed={device
              ? (device.role === 'sender' ? sender : receiver)?.id === n.id
              : selectedNode === n.id}
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
            onclick={() => selectNode(n.id)}
            onkeydown={(ev) => handleKey(ev, () => selectNode(n.id))}
          >
            <title
              >{n.label} · {n.id} · {n.simulated_address} · {n.online
                ? 'online'
                : 'offline'}</title
            >
            {#if !device && pinnedNodes.has(n.id)}
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
            {#if device}
              <defs
                ><clipPath id={'portrait-' + device.id}
                  ><circle r={g.w / 2 - 2} /></clipPath
                ></defs
              >
              <circle class="avatar-ring" data-card="" r={g.w / 2} />
              <image
                href={avatarUrl(device.id)}
                x={-g.w / 2}
                y={-g.h / 2}
                width={g.w}
                height={g.h}
                clip-path={'url(#portrait-' + device.id + ')'}
                preserveAspectRatio="xMidYMid slice"
              />
              <text class="avatar-name" text-anchor="middle" y={g.h / 2 + 13}
                >{device.label}</text
              >
            {:else}
              <rect
                data-card=""
                class="card"
                x={-g.w / 2}
                y={-g.h / 2}
                width={g.w}
                height={g.h}
                rx="5"
              />
              <g transform="translate(-8,-8) scale(.67)"
                ><GraphGlyph kind={n.kind} /></g
              >
              <text class="node-label" text-anchor="middle" y={g.h / 2 + 13}
                >{isChannel(n.kind)
                  ? n.kind === 'direct'
                    ? 'Direct'
                    : channelNames[n.kind]
                  : n.kind === 'provider'
                    ? n.label.replace(' provider', '')
                    : n.label}</text
              >
            {/if}
            {#if activity}
              <g
                class="endpoints"
                transform={'translate(0 ' + (-g.h / 2 - 14) + ')'}
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
            transitFraction(
              markerTimes[m.id] ?? lab.simulation_time_ms,
              m.t.start_ms,
              m.t.end_ms,
            ),
          )}
          <g
            class="marker"
            class:background={!m.leg && !m.poll}
            data-poll-id={m.poll ? m.t.token : undefined}
            data-message-id={m.leg?.messageId}
            data-transit-id={m.id}
            data-retry={m.retry}
            data-source={m.t.source}
            data-target={m.t.target}
            data-lane={m.t.lane}
            transform={'translate(' + pos.x + ' ' + pos.y + ')'}
            pointer-events="none"
          >
            <title
              >{m.poll ? 'Mailbox poll ' + m.t.token : m.t.token} · {m.t.source} →
              {m.t.target} · {m.t.start_ms}–{m.t.end_ms} ms</title
            >
            <circle
              r={m.leg
                ? Math.min(17, 7.5 / zoom)
                : m.poll
                  ? Math.min(10, 3.5 / zoom)
                  : 3}
              fill={m.leg ? 'white' : m.retry ? '#fff0dd' : '#d6f4df'}
              stroke={m.retry
                ? '#c0580a'
                : (m.colour ?? (m.poll ? '#355679' : '#77867c'))}
              stroke-width={m.leg ? 2 : 1}
            /><circle
              r={m.leg ? Math.min(10, 4.4 / zoom) : 1.2}
              fill={m.colour ?? '#6b7f72'}
            />
            {#if m.leg}
              <circle
                r={Math.min(20, 9 / zoom)}
                fill="transparent"
                class="marker-hit"
                pointer-events="all"
                role="button"
                tabindex="0"
                aria-label={'Inspect ' + m.leg.messageId + ' ' + m.id}
                onclick={() => chooseLeg(m.leg!)}
                onkeydown={(ev) => handleKey(ev, () => chooseLeg(m.leg!))}
              />
            {/if}
          </g>
        {/each}
      </svg>
    </div>
    {#key lab.simulation_id + '/' + lab.epoch + '/' + receiver?.id}
      <ConversationColumn
        role="receiver"
        devices={lab.devices}
        messages={lab.messages}
        selectedId={receiver?.id}
        address={liveNodes.get(receiver?.id ?? '')?.simulated_address}
      />
    {/key}
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
  {#if selectedLeg && selectedLeg.pathId === selectedPath && pickedTrack}
    <section
      class="leg-readout"
      aria-label="Recorded message transit"
      data-selected-leg={selectedLeg.id}
      style:--message-colour={pickedTrack.colour}
    >
      <div class="leg-title">
        <strong>{selectedLeg.messageId}</strong><span
          >{selectedLeg.source} → {selectedLeg.target}</span
        >
        <button aria-label="Close transit details" onclick={() => (pick = null)}
          >×</button
        >
      </div>
      {#if selectedLeg.ipHop}
        <IPObservation
          hop={selectedLeg.ipHop}
          observation={selectedLeg.event.payload.ip_observation ?? null}
          proxyEgress={[
            liveNodes.get(selectedLeg.source),
            liveNodes.get(selectedLeg.target),
          ].find((n) => n?.kind === 'shadowsocks')?.egress_address}
          heading="Recorded IP visibility"
        />
      {:else}<p>
          The backend did not record IP visibility for this transit.
        </p>{/if}
      {#if pickedTrack.legs.length > 1}
        <label
          >Traversal <select
            value={selectedLeg.id}
            onchange={(e) => chooseLeg(traces.legs.get(e.currentTarget.value)!)}
          >
            {#each pickedTrack.legs as id (id)}
              {@const row = traces.legs.get(id)!}
              <option value={id}
                >{id} · {row.startMs ?? row.endMs} ms · {row.status}</option
              >
            {/each}
          </select></label
        >
      {/if}
      <dl>
        <dt>Transit</dt>
        <dd>{selectedLeg.id} · {selectedLeg.status}</dd>
        <dt>Path</dt>
        <dd>
          {selectedLeg.pathId} · {pathMap.get(selectedLeg.pathId)
            ?.transport_label}
        </dd>
        <dt>Direction</dt>
        <dd>{selectedLeg.lane}</dd>
        <dt>Token</dt>
        <dd>{selectedLeg.token}</dd>
        {#if selectedLeg.startMs !== null}<dt>Departure</dt>
          <dd>{selectedLeg.startMs} ms</dd>{/if}
        {#if selectedLeg.expectedEndMs !== null}<dt>Expected arrival</dt>
          <dd>{selectedLeg.expectedEndMs} ms</dd>{/if}
        {#if selectedLeg.endMs !== null}<dt>
            {selectedLeg.status === 'failed' ? 'Failure' : 'Arrival'}
          </dt>
          <dd>{selectedLeg.endMs} ms</dd>{/if}
        {#if selectedLeg.startMs !== null && selectedLeg.endMs !== null}<dt>
            Elapsed
          </dt>
          <dd>{selectedLeg.endMs - selectedLeg.startMs} ms</dd>{/if}
        {#if selectedLeg.reason}<dt>Reason</dt>
          <dd>{selectedLeg.reason}</dd>{/if}
        {#each Object.entries(selectedLeg.cargo) as [field, value] (field)}
          <dt>{field.replaceAll('_', ' ')}</dt>
          <dd>
            {typeof value === 'object' ? JSON.stringify(value) : String(value)}
          </dd>
        {:else}<dt>Cargo</dt>
          <dd>No recorded description</dd>{/each}
      </dl>
    </section>
  {:else if expanded && highlight}
    <div class="screen-addresses">
      <PathAddresses path={highlight} nodes={lab.topology.nodes} />
    </div>
  {/if}
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
  .diagram-layout {
    display: grid;
    grid-template-columns: clamp(154px, 13vw, 262px) minmax(0, 1fr) clamp(
        154px,
        13vw,
        262px
      );
    grid-template-rows: minmax(0, 1fr);
    height: clamp(350px, 57vh, 620px);
    min-height: 0;
  }
  .diagram-layout > :global(aside:first-child) {
    border-right: 1px solid var(--border);
  }
  .diagram-layout > :global(aside:last-child) {
    border-left: 1px solid var(--border);
  }
  .screen-button {
    font-size: 0.74rem;
    min-height: 30px;
    padding: 4px 9px;
  }
  .network-panel.expanded {
    position: fixed;
    inset: 0;
    z-index: 1000;
    width: 100%;
    height: 100dvh;
    border: 0;
    border-radius: 0;
    display: flex;
    flex-direction: column;
    overflow: auto;
  }
  .expanded .diagram-layout > :global(aside) {
    display: none;
  }
  .expanded .diagram-layout {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: minmax(0, 1fr);
    flex: 1;
    min-height: 0;
    height: auto;
  }
  .expanded .graph-head,
  .expanded .legend {
    flex-shrink: 0;
  }
  .expanded .graph-viewport {
    max-height: none;
  }
  :global(body:has(.network-panel.expanded)) {
    overflow: hidden;
  }
  @media (max-width: 850px) {
    .diagram-layout {
      grid-template-columns: repeat(2, minmax(0, 1fr));
      grid-template-rows: minmax(260px, 1fr) minmax(175px, 0.7fr);
      height: min(82vh, 760px);
    }
    .diagram-layout .graph-viewport {
      grid-row: 1;
      grid-column: 1/-1;
    }
    .diagram-layout > :global(aside) {
      grid-row: 2;
      border-top: 1px solid var(--border);
    }
    .diagram-layout > :global(aside:last-child) {
      border-left: 0;
    }
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
    max-height: none;
    min-width: 0;
    min-height: 0;
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
  .band.tor rect,
  .band.shadowsocks rect,
  .band.direct rect {
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
    stroke-width: 0.65;
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
    stroke-width: 1;
    stroke-dasharray: none;
    opacity: 0.92;
  }
  .edge.active .stroke {
    stroke: #388653;
    stroke-width: 1.1;
    stroke-dasharray: none;
    opacity: 1;
  }
  .edge.failed .stroke,
  .edge.blocked .stroke {
    stroke: #b9493a;
    stroke-dasharray: 6 3;
    opacity: 0.95;
    stroke-width: 0.9;
  }
  .edge.unavailable .stroke {
    stroke: #b08774;
    stroke-dasharray: 1 5;
  }
  .edge:hover .stroke,
  .edge:focus-visible .stroke,
  .edge[aria-pressed='true'] .stroke {
    stroke-width: 1.5;
    opacity: 1;
  }
  .pinned-route {
    fill: none;
    stroke: #3e54c0;
    stroke-width: 1.5;
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
  .edge.substrate.completed .stroke,
  .edge.substrate.configured .stroke {
    stroke: #a3afa7;
    opacity: 0.3;
  }
  .edge.substrate.active .stroke {
    stroke: #728d7f;
    stroke-width: 0.75;
    opacity: 0.36;
  }
  .marker-hit {
    cursor: pointer;
  }
  .edge.context.active .stroke,
  .edge.context.completed .stroke {
    stroke: #a3afa7;
    stroke-width: 1;
    opacity: 0.3;
  }
  .marker.background {
    opacity: 0.35;
  }
  .message-track {
    cursor: pointer;
    outline: none;
  }
  .message-track path {
    fill: none;
  }
  .message-halo {
    stroke: #fff;
    stroke-width: 2.4;
    pointer-events: none;
  }
  .message-track path,
  .history-dot {
    vector-effect: non-scaling-stroke;
  }
  .message-hit {
    stroke: transparent;
    stroke-width: 13;
    pointer-events: stroke;
  }
  .message-line {
    stroke: var(--message-colour);
    stroke-width: 1.25;
    pointer-events: none;
  }
  .message-track.failed .message-line {
    stroke-dasharray: 4 3;
  }
  .message-track:hover .message-line,
  .message-track:focus-visible .message-line,
  .message-track.chosen .message-line {
    stroke-width: 1.75;
  }
  .history-dot {
    fill: var(--message-colour);
    stroke: white;
    stroke-width: 1.2;
  }
  .screen-addresses {
    padding: 0 1rem;
  }
  .leg-readout {
    margin: 8px 16px 14px;
    border-left: 3px solid var(--message-colour);
    padding: 6px 10px;
    max-height: 220px;
    overflow: auto;
    background: #f6f8f6;
  }
  .leg-title {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
  }
  .leg-title strong {
    color: var(--message-colour);
  }
  .leg-title button {
    margin-left: auto;
    background: white;
    border: 1px solid #d3dbd5;
    border-radius: 3px;
  }
  .leg-readout dl {
    display: grid;
    grid-template-columns: max-content minmax(0, 1fr);
    gap: 2px 9px;
    font-size: 11px;
    margin: 6px 0 0;
  }
  .leg-readout dt {
    color: #51645a;
  }
  .leg-readout dd {
    margin: 0;
    overflow-wrap: anywhere;
    font-family: var(--mono, monospace);
  }
  .leg-readout label {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 11px;
    margin: 4px 0;
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
  .avatar-ring {
    fill: white;
    stroke: #a9b6ad;
    stroke-width: 1.5;
  }
  .graph-node[aria-pressed='true'] .avatar-ring {
    stroke: #208346;
    stroke-width: 3.5;
  }
  .graph-node:focus-visible .avatar-ring {
    stroke-dasharray: 4 2;
  }
  .avatar-name {
    fill: #2e4437;
    font:
      650 11px system-ui,
      sans-serif;
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
