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
import type {
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

function metrics(node: LabNode, count: number) {
  if (node.kind === 'person') return { w: 146, h: 88, cols: 1 };
  if (node.kind === 'storage' || node.kind === 'dht')
    return { w: 60, h: 44, cols: count > 6 ? 2 : 1 };
  if (node.kind === 'mix') return { w: 55, h: 44, cols: 1 };
  return { w: 68, h: 48, cols: 1 };
}

export function layoutTopology(nodes: LabNode[], paths: Path[]): GraphLayout {
  const stages: StageBand[] = [];
  const points: GraphNode[] = [];
  const groups = Array.from(group(nodes, (n) => n.stage_index)).sort(
    ([a], [b]) => a - b,
  );
  const plans = groups.map(([index, entries]) => {
    const m = metrics(entries[0], entries.length);
    const rows = Math.ceil(entries.length / m.cols);
    return {
      index,
      entries,
      ...m,
      rows,
      extent: rows * m.h + Math.max(0, rows - 1) * 15,
    };
  });
  const body = Math.max(280, ...plans.map((p) => p.extent));
  const height = body + 132;
  let x = 14;
  for (const p of plans) {
    const width = p.cols * p.w + (p.cols - 1) * 11 + 28;
    const kind = p.entries[0].kind;
    stages.push({
      index: p.index,
      name: p.entries[0].stage,
      x,
      width,
      count: p.entries.length,
      kind,
    });
    p.entries.forEach((n, i) => {
      const cx = x + 14 + p.w / 2 + (i % p.cols) * (p.w + 11);
      const cy =
        68 +
        Math.min(70, (body - p.extent) / 2) +
        p.h / 2 +
        Math.floor(i / p.cols) * (p.h + 15);
      points.push({ id: n.id, x: cx, y: cy, cx, cy, w: p.w, h: p.h });
    });
    x += width + 9;
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
  return { width: x + 5, height, nodes: anchors, stages };
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
  let messages = messageTrafficHistory();
  let plannedPacket: string | undefined;
  let epochKey = '',
    last = 0;
  let seen = new Map<string, Trace>(),
    chosen = new Map<string, Trace>();
  return function history(key: string, rows: LabEvent[]) {
    if (epochKey !== key || rows.length < last) {
      epochKey = key;
      last = 0;
      plannedPacket = undefined;
      retries.clear();
      messages = messageTrafficHistory();
      seen = new Map();
      chosen = new Map();
    }
    for (let i = last; i < rows.length; i++) {
      const e = rows[i],
        p = e.payload;
      const lane = p.lane === 'reply' ? 'reply' : 'forward';
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
        seen.set(p.path_id, {
          source: e.source_id,
          target: e.target_id,
          lane,
          failed: e.event_type === 'path_transit_failed',
          at: e.simulation_time_ms,
        });
      }
    }
    last = rows.length;
    return {
      seen,
      chosen,
      retries,
      legs: messages.legs,
      messageTracks: messages.tracks,
    };
  };
}
