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
import type { Direction, LabNode, NodeDetails, Path } from './types';

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
  if (node.kind === 'person') return { w: 146, h: 122, cols: 1 };
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
        (body - p.extent) / 2 +
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
export function laneCurve(a: GraphNode, b: GraphNode, lane: Direction): Curve {
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
