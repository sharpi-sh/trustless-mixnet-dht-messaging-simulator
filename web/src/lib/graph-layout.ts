import {
  forceCollide,
  forceLink,
  forceSimulation,
  forceX,
  forceY,
  group,
  path as d3path,
  type SimulationNodeDatum,
} from 'd3';
import { recordedIPHop } from './channels';
import type {
  IPHop,
  ActiveTransit,
  Direction,
  LabEvent,
  LabNode,
  Json,
  NodeDetails,
  Path,
} from './types';

export interface GraphNode extends SimulationNodeDatum {
  id: string;
  x: number;
  y: number;
  cx: number;
  cy: number;
  w: number;
  h: number;
  circular?: boolean;
}
export interface StageBand {
  index: number;
  name: string;
  x: number;
  width: number;
  count: number;
  kind: LabNode['kind'];
}
export interface GraphLayout {
  width: number;
  height: number;
  nodes: Map<string, GraphNode>;
  stages: StageBand[];
}
type Point = { x: number; y: number };

function metrics(kind: LabNode['kind']) {
  if (kind === 'storage' || kind === 'dht') return { w: 30, h: 22 };
  if (kind === 'shadowsocks') return { w: 66, h: 24 };
  if (kind === 'mix') return { w: 28, h: 22 };
  return { w: 34, h: 24 };
}

export function layoutTopology(
  nodes: LabNode[],
  paths: Path[],
  viewport?: { width: number; height: number },
): GraphLayout {
  const stages: StageBand[] = [];
  const points: GraphNode[] = [];
  const groups = Array.from(group(nodes, (n) => n.stage_index)).sort(
    ([a], [b]) => a - b,
  );
  const networks = groups.filter(([, entries]) => entries[0].kind !== 'person');
  const people = groups.filter(([, entries]) => entries[0].kind === 'person');
  const avatarDiameter = 40,
    avatarPitch = 72,
    avatarGutter = 60;
  const firstNetwork = networks[0]?.[0] ?? 1;
  const left = people
    .filter(([index]) => index < firstNetwork)
    .flatMap(([, entries]) => entries);
  const right = people
    .filter(([index]) => index >= firstNetwork)
    .flatMap(([, entries]) => entries);
  const leftMargin = left.length ? avatarGutter : 10;
  const rightMargin = right.length ? avatarGutter : 10;
  const insetX = 14,
    bandGap = 7,
    columnGap = 35,
    rowGap = 38;
  const top = 56,
    bottom = 32;
  function plan(rowLimit: number) {
    const bands = networks.map(([index, entries]) => {
      const kind = entries[0].kind;
      const { w, h } = metrics(kind);
      const cols =
        kind === 'storage' || kind === 'dht'
          ? Math.ceil(entries.length / rowLimit)
          : 1;
      const rows = Math.ceil(entries.length / cols);
      return {
        index,
        entries,
        kind,
        w,
        h,
        cols,
        rows,
        width: Math.max(110, cols * w + (cols - 1) * columnGap + 2 * insetX),
        height: rows * h + (rows - 1) * rowGap,
      };
    });
    return {
      bands,
      width:
        leftMargin +
        rightMargin +
        bands.reduce((sum, p) => sum + p.width + bandGap, 0) -
        bandGap,
      height: Math.max(
        top + Math.max(100, ...bands.map((p) => p.height)) + bottom,
        Math.max(left.length, right.length) * avatarPitch + 30,
      ),
    };
  }
  let chosen = plan(6);
  let width = chosen.width,
    height = chosen.height;
  if (viewport && viewport.width > 0 && viewport.height > 0) {
    // Try DHT and vault row counts and keep the largest uniform card scale
    // that fits both dimensions. Stage ordering stays stable on every resize.
    const score = (p: typeof chosen) =>
      Math.min(viewport.width / p.width, viewport.height / p.height);
    let scale = score(chosen);
    const maxRows = Math.max(
      1,
      ...groups
        .filter(
          ([, entries]) =>
            entries[0].kind === 'dht' || entries[0].kind === 'storage',
        )
        .map(([, entries]) => entries.length),
    );
    for (let rows = 1; rows <= maxRows; rows++) {
      const candidate = plan(rows);
      const candidateScale = score(candidate);
      if (candidateScale > scale) {
        chosen = candidate;
        scale = candidateScale;
      }
    }
    width = viewport.width / scale;
    height = viewport.height / scale;
  }
  const body = height - top - bottom;
  const extraWidth = (width - chosen.width) / Math.max(1, chosen.bands.length);
  let x = leftMargin;
  for (const p of chosen.bands) {
    const bandWidth = p.width + extraWidth;
    stages.push({
      index: p.index,
      name: p.entries[0].stage,
      x,
      width: bandWidth,
      count: p.entries.length,
      kind: p.kind,
    });
    p.entries.forEach((n, i) => {
      const cx = x + (((i % p.cols) + 0.5) * bandWidth) / p.cols;
      const cy =
        top +
        (p.rows === 1
          ? body / 2
          : p.h / 2 + (Math.floor(i / p.cols) * (body - p.h)) / (p.rows - 1));
      points.push({ id: n.id, x: cx, y: cy, cx, cy, w: p.w, h: p.h });
    });
    x += bandWidth + bandGap;
  }
  for (const [entries, cx] of [
    [left, avatarGutter / 2],
    [right, width - avatarGutter / 2],
  ] as const) {
    entries.forEach((n, i) => {
      const cy = height / 2 + (i - (entries.length - 1) / 2) * avatarPitch;
      points.push({
        id: n.id,
        x: cx,
        y: cy,
        cx,
        cy,
        fx: cx,
        fy: cy,
        w: avatarDiameter,
        h: avatarDiameter,
        circular: true,
      });
    });
  }
  // Column anchors constrain the small link/collision adjustment, even at 64 DHT peers.
  const anchors = new Map(points.map((n) => [n.id, n]));
  const near = paths
    .filter((p) => {
      const a = anchors.get(p.source_id),
        b = anchors.get(p.target_id);
      return a && b && Math.abs(a.cx - b.cx) < 170;
    })
    .map((p) => ({ source: p.source_id, target: p.target_id }));
  const sim = forceSimulation(points)
    .stop()
    .force('x', forceX<GraphNode>((n) => n.cx).strength(0.94))
    .force('y', forceY<GraphNode>((n) => n.cy).strength(0.85))
    .force(
      'collision',
      forceCollide<GraphNode>((n) => Math.min(n.w, n.h) / 2 + 4).iterations(2),
    )
    .force(
      'local',
      forceLink<GraphNode, { source: string; target: string }>(near)
        .id((n) => n.id)
        .strength(0.012)
        .distance(90),
    )
    .alpha(0.22)
    .alphaDecay(0.16);
  sim.tick(26);
  points.forEach((n) => {
    n.x = Math.round(Math.max(n.cx - 2, Math.min(n.cx + 2, n.x)));
    n.y = Math.round(Math.max(n.cy - 4, Math.min(n.cy + 4, n.y)));
  });
  return { width, height, nodes: anchors, stages };
}

export interface Curve {
  start: Point;
  c1: Point;
  c2: Point;
  end: Point;
  d: string;
}
export function laneCurve(
  a: GraphNode,
  b: GraphNode,
  lane: Direction,
  offset = 0,
): Curve {
  const sign = lane === 'reply' ? 1 : -1;
  const dx = b.x - a.x;
  let start: Point, end: Point, c1: Point, c2: Point;
  if (Math.abs(dx) < 15) {
    const bend = lane === 'reply' ? -1 : 1;
    start = { x: a.x + (bend * a.w) / 2, y: a.y };
    end = { x: b.x + (bend * b.w) / 2, y: b.y };
    const x = start.x + bend * (12 + Math.min(28, Math.abs(b.y - a.y) * 0.13));
    c1 = { x, y: start.y };
    c2 = { x, y: end.y };
  } else {
    const dir = Math.sign(dx);
    start = { x: a.x + (dir * a.w) / 2, y: a.y + sign * Math.min(12, a.h / 4) };
    end = { x: b.x - (dir * b.w) / 2, y: b.y + sign * Math.min(12, b.h / 4) };
    const spread = Math.min(36, Math.abs(end.x - start.x) * 0.32);
    const arc =
      lane === 'reply'
        ? Math.min(52, Math.abs(dx) * 0.13)
        : Math.min(18, Math.abs(dx) * 0.035);
    c1 = { x: start.x + dir * spread, y: start.y + sign * arc };
    c2 = { x: end.x - dir * spread, y: end.y + sign * arc };
  }
  // Parallel message tracks keep distinct ports on the same pair of node cards.
  const clampPort = (value: number, centre: number, height: number) =>
    Math.max(
      centre - height / 2 + 3,
      Math.min(centre + height / 2 - 3, value + offset),
    );
  start.y = clampPort(start.y, a.y, a.h);
  end.y = clampPort(end.y, b.y, b.h);
  if (Math.abs(dx) >= 15) {
    for (const [point, node, side] of [
      [start, a, Math.sign(dx)],
      [end, b, -Math.sign(dx)],
    ] as const) {
      if (node.circular) {
        const dy = point.y - node.y;
        point.x = node.x + side * Math.sqrt((node.w / 2) ** 2 - dy ** 2);
      }
    }
  }
  if (Math.abs(dx) < 15) {
    c1.x += offset;
    c2.x += offset;
    c1.y = start.y;
    c2.y = end.y;
  } else {
    c1.y += offset;
    c2.y += offset;
  }
  const path = d3path();
  path.moveTo(start.x, start.y);
  path.bezierCurveTo(c1.x, c1.y, c2.x, c2.y, end.x, end.y);
  return { start, c1, c2, end, d: path.toString() };
}
export function onCurve(curve: Curve, t: number): Point {
  const s = 1 - t,
    w1 = s * s * s,
    w2 = 3 * s * s * t,
    w3 = 3 * s * t * t,
    w4 = t * t * t;
  return {
    x:
      w1 * curve.start.x + w2 * curve.c1.x + w3 * curve.c2.x + w4 * curve.end.x,
    y:
      w1 * curve.start.y + w2 * curve.c1.y + w3 * curve.c2.y + w4 * curve.end.y,
  };
}
export function transitFraction(
  now: number,
  start: number,
  end: number,
): number {
  // Even a zero-duration hop stays visible until Python removes it from the active path.
  return end <= start
    ? 0.5
    : Math.max(0.035, Math.min(0.965, (now - start) / (end - start)));
}
export function contactIds(
  details: NodeDetails | null,
  selected: string,
): Set<string> {
  const ids = new Set<string>();
  if (!details || details.node.id !== selected) return ids;
  const rows = details.state.buckets;
  if (details.node.kind === 'dht' && Array.isArray(rows))
    for (const bucket of rows) {
      if (
        !bucket ||
        typeof bucket !== 'object' ||
        Array.isArray(bucket) ||
        !Array.isArray(bucket.contacts)
      )
        continue;
      for (const c of bucket.contacts)
        if (
          c &&
          typeof c === 'object' &&
          !Array.isArray(c) &&
          typeof c.peer === 'string'
        )
          ids.add(c.peer);
    }
  if (details.node.kind === 'mix')
    for (const id of Object.keys(details.node.adjacent_peers ?? {}))
      ids.add(id);
  return ids;
}

const edgeId = (a: string, b: string) => [a, b].sort().join('~');

export function extractRoute(event?: LabEvent | null) {
  if (!event || event.event_type !== 'mixnet_route_constructed') return null;
  const { ordered_route, lane, attempt, packet_id } = event.payload;
  if (
    typeof packet_id !== 'string' ||
    !Array.isArray(ordered_route) ||
    !ordered_route.every((id): id is string => typeof id === 'string') ||
    ordered_route.length < 2
  )
    return null;
  const direction: Direction = lane === 'reply' ? 'reply' : 'forward';
  const legs = ordered_route.slice(1).map((target, i) => ({
    id: edgeId(ordered_route[i], target),
    source: ordered_route[i],
    target,
    lane: direction,
  }));
  return {
    nodes: ordered_route,
    legs,
    retry: typeof attempt === 'number' && attempt > 1,
    packet: packet_id,
  };
}

export function transitEndpoints(
  transits: ActiveTransit[],
  retries: ReadonlySet<string>,
) {
  const result = new Map<
    string,
    {
      outgoing: number;
      incoming: number;
      outgoingRetries: number;
      incomingRetries: number;
    }
  >();
  function entry(id: string) {
    let row = result.get(id);
    if (!row) {
      row = {
        outgoing: 0,
        incoming: 0,
        outgoingRetries: 0,
        incomingRetries: 0,
      };
      result.set(id, row);
    }
    return row;
  }
  for (const t of transits) {
    const src = entry(t.source),
      dst = entry(t.target);
    src.outgoing++;
    dst.incoming++;
    if (retries.has(t.token)) {
      src.outgoingRetries++;
      dst.incomingRetries++;
    }
  }
  return result;
}

const messagePalette = [
  '#1954ac',
  '#ac2c68',
  '#00775f',
  '#9c4b03',
  '#7540a8',
  '#087186',
  '#a72e38',
  '#65760e',
  '#4b4ca5',
  '#a34412',
  '#097085',
  '#6f497b',
];

export function messageColour(id: string): string {
  const suffix = /^msg-(\d+)$/.exec(id);
  let index = suffix ? Math.max(0, Number(suffix[1]) - 1) : 0;
  if (!suffix) for (const c of id) index = (31 * index + c.charCodeAt(0)) >>> 0;
  if (index < messagePalette.length) return messagePalette[index];
  return `hsl(${((index * 137.508) % 360).toFixed(2)} 66% 37%)`;
}

export interface MessageLeg {
  id: string;
  messageId: string;
  pathId: string;
  token: string;
  lane: Direction;
  source: string;
  target: string;
  startMs: number | null;
  expectedEndMs: number | null;
  endMs: number | null;
  status: 'active' | 'completed' | 'failed';
  reason: string | null;
  cargo: Record<string, Json>;
  ipHop: IPHop | null;
  event: LabEvent;
}
interface MessageTrack {
  id: string;
  messageId: string;
  pathId: string;
  source: string;
  target: string;
  lane: Direction;
  offset: number;
  legs: string[];
}

// Completed traces keep their geometry while other cells move. A resize creates a
// new layout, and a changed transit status supplies a new MessageLeg object.
export function makeTrackRenderer(layout: GraphLayout) {
  function render(
    track: MessageTrack,
    latest: MessageLeg,
    a: GraphNode,
    b: GraphNode,
  ) {
    const curve = laneCurve(a, b, track.lane, track.offset);
    return {
      ...track,
      latest,
      curve,
      dot: onCurve(curve, 0.5),
      colour: messageColour(track.messageId),
    };
  }
  const cache = new WeakMap<MessageLeg, ReturnType<typeof render>>();
  return (track: MessageTrack, latest: MessageLeg) => {
    const cached = cache.get(latest);
    if (cached) return cached;
    const a = layout.nodes.get(track.source),
      b = layout.nodes.get(track.target);
    if (!a || !b) return;
    const rendered = render(track, latest, a, b);
    cache.set(latest, rendered);
    return rendered;
  };
}

function messageTrafficHistory() {
  const legs = new Map<string, MessageLeg>();
  const tracks = new Map<string, MessageTrack>();
  const sharedOffsets = new Map<string, Map<string, number>>();
  function add(event: LabEvent) {
    const p = event.payload;
    if (
      !event.message_id ||
      !event.source_id ||
      !event.target_id ||
      typeof p.transit_id !== 'string' ||
      typeof p.path_id !== 'string' ||
      typeof p.token !== 'string'
    )
      return;
    const status =
      event.event_type === 'path_transit_started'
        ? 'active'
        : event.event_type === 'path_transit_completed'
          ? 'completed'
          : event.event_type === 'path_transit_failed'
            ? 'failed'
            : null;
    if (!status) return;
    const lane = p.lane === 'reply' ? 'reply' : 'forward';
    const existing = legs.get(p.transit_id);
    if (existing) {
      if (status !== 'active') {
        legs.set(existing.id, {
          ...existing,
          ipHop: existing.ipHop ?? recordedIPHop(p.ip_hop),
          status,
          endMs: event.simulation_time_ms,
          event,
          reason: typeof p.reason === 'string' ? p.reason : null,
        });
      }
      return;
    }
    const leg: MessageLeg = {
      id: p.transit_id,
      pathId: p.path_id,
      token: p.token,
      messageId: event.message_id,
      source: event.source_id,
      target: event.target_id,
      lane,
      status,
      ipHop: recordedIPHop(p.ip_hop),
      cargo:
        p.cargo && typeof p.cargo === 'object' && !Array.isArray(p.cargo)
          ? p.cargo
          : {},
      startMs:
        status === 'active'
          ? typeof p.start_ms === 'number'
            ? p.start_ms
            : event.simulation_time_ms
          : null,
      expectedEndMs: typeof p.end_ms === 'number' ? p.end_ms : null,
      endMs: status === 'active' ? null : event.simulation_time_ms,
      reason: typeof p.reason === 'string' ? p.reason : null,
      event,
    };
    legs.set(leg.id, leg);
    const band = leg.pathId + '/' + lane;
    const id = band + '/' + leg.source + '/' + leg.messageId;
    let track = tracks.get(id);
    if (!track) {
      let offsets = sharedOffsets.get(band);
      if (!offsets) {
        offsets = new Map();
        sharedOffsets.set(band, offsets);
      }
      if (!offsets.has(leg.messageId)) {
        const i = offsets.size;
        offsets.set(
          leg.messageId,
          (i % 2 === 0 ? -1 : 1) * 10 * Math.ceil(i / 2),
        );
      }
      track = {
        id,
        messageId: leg.messageId,
        pathId: leg.pathId,
        source: leg.source,
        target: leg.target,
        lane,
        offset: offsets.get(leg.messageId)!,
        legs: [],
      };
      tracks.set(id, track);
    }
    track.legs.push(leg.id);
  }
  return { add, legs, tracks };
}

export function makeTraceHistory() {
  type Trace = {
    source: string;
    target: string;
    lane: Direction;
    failed: boolean;
    at: number;
  };
  const retries = new Set<string>();
  const pollStarts = new Map<string, number>();
  const pollResults = new Map<string, string>();
  let messages = messageTrafficHistory();
  let plannedPacket: string | undefined;
  let epochKey = '',
    lastSequence = 0,
    firstSequence = Infinity;
  let seen = new Map<string, Trace>(),
    seenMessages = new Map<string, Trace>(),
    chosen = new Map<string, Trace>();
  return function history(key: string, rows: LabEvent[]) {
    const first = rows[0]?.sequence ?? Infinity;
    const end = rows.at(-1)?.sequence ?? 0;
    // A reconnect can backfill a full prefix after the graph first saw a partial window.
    const backfilled = first < firstSequence && end >= lastSequence;
    if (epochKey !== key || backfilled) {
      epochKey = key;
      lastSequence = 0;
      firstSequence = first;
      plannedPacket = undefined;
      retries.clear();
      pollStarts.clear();
      pollResults.clear();
      messages = messageTrafficHistory();
      seen = new Map();
      seenMessages = new Map();
      chosen = new Map();
    }
    // Frames can overlap, shrink or slide at a fixed length within one epoch.
    // Find new server sequence numbers without rescanning the full replay on every step.
    let low = 0,
      high = rows.length;
    while (low < high) {
      const middle = Math.floor((low + high) / 2);
      if (rows[middle].sequence <= lastSequence) low = middle + 1;
      else high = middle;
    }
    for (let i = low; i < rows.length; i++) {
      const e = rows[i],
        p = e.payload;
      const lane = p.lane === 'reply' ? 'reply' : 'forward';
      if (e.event_type === 'poll_started' && e.source_id)
        pollStarts.set(e.source_id, e.simulation_time_ms);
      if (typeof p.person_id === 'string') {
        const result =
          e.event_type === 'poll_empty'
            ? 'Empty'
            : e.event_type === 'poll_failed'
              ? 'Failed'
              : e.event_type === 'poll_message_found'
                ? `${p.found} found`
                : null;
        if (result)
          pollResults.set(
            p.person_id,
            result + ' at ' + e.simulation_time_ms + ' ms',
          );
      }
      const route = extractRoute(e);
      if (route?.retry) retries.add(route.packet);
      if (route && e.message_id) {
        plannedPacket = route.packet;
        chosen = new Map(
          route.legs.map((leg) => [
            leg.id,
            { ...leg, failed: false, at: e.simulation_time_ms },
          ]),
        );
      }
      if (
        plannedPacket &&
        p.packet_id === plannedPacket &&
        (e.event_type === 'message_forward_failed' ||
          (e.event_type === 'sphinx_layer_processed' && p.next_id === null))
      ) {
        chosen = new Map();
        plannedPacket = undefined;
      }
      if (
        e.event_type.startsWith('path_transit_') &&
        typeof p.path_id === 'string' &&
        e.source_id &&
        e.target_id
      ) {
        messages.add(e);
        const observation = {
          source: e.source_id,
          target: e.target_id,
          lane,
          failed: e.event_type === 'path_transit_failed',
          at: e.simulation_time_ms,
        } satisfies Trace;
        seen.set(p.path_id, observation);
        if (e.message_id) seenMessages.set(p.path_id, observation);
      }
    }
    lastSequence = Math.max(lastSequence, end);
    return {
      seen,
      seenMessages,
      pollStarts,
      pollResults,
      chosen,
      retries,
      legs: messages.legs,
      messageTracks: messages.tracks,
    };
  };
}
