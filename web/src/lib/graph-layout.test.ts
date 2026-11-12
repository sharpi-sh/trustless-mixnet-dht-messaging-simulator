import { expect, test } from 'vitest';
import {
  contactIds,
  laneCurve,
  layoutTopology,
  onCurve,
  transitFraction,
} from './graph-layout';
import type { LabNode, NodeDetails, Path } from './types';

function node(id: string, kind: LabNode['kind'], stage_index: number): LabNode {
  return {
    id,
    kind,
    stage_index,
    label: id,
    stage: kind,
    simulated_address: 'local',
    operator_id: 'operator',
    online: true,
    history: [],
    last_activity: null,
    failure_count: 0,
  };
}
function path(a: string, b: string): Path {
  return {
    id: [a, b].sort().join('~'),
    source_id: a,
    target_id: b,
    boundary: 'test',
    transport_label: 'Loopix datagram',
    base_transit_delay_ms: 7,
    jitter_min_ms: 0,
    jitter_max_ms: 0,
    blocked: false,
    blocked_at: null,
    blocked_by: null,
    active: {},
    attempted: 0,
    completed: 0,
    failed: 0,
    dropped: 0,
  };
}

test('keeps stage order and card bounds stable under changing node and path state', () => {
  const nodes: LabNode[] = [node('alice', 'person', 0), node('tor', 'tor', 1)];
  for (let i = 0; i < 20; i++) nodes.push(node('mix-' + i, 'mix', 2 + (i % 3)));
  for (let i = 0; i < 64; i++) nodes.push(node('dht-' + i, 'dht', 5));
  for (let i = 0; i < 32; i++) nodes.push(node('storage-' + i, 'storage', 6));
  const paths = [
    path('alice', 'tor'),
    path('tor', 'mix-0'),
    path('mix-0', 'mix-1'),
  ];
  const layout = layoutTopology(nodes, paths);
  expect(layout.nodes.size).toBe(nodes.length);
  expect(layout.nodes.get('alice')!.y).toBeLessThan(210);
  expect(layout.stages.map((s) => s.index)).toEqual([0, 1, 2, 3, 4, 5, 6]);
  for (const n of nodes) {
    const p = layout.nodes.get(n.id)!,
      stage = layout.stages.find((s) => s.index === n.stage_index)!;
    expect(p.x - p.w / 2).toBeGreaterThan(stage.x);
    expect(p.x + p.w / 2).toBeLessThan(stage.x + stage.width);
    expect(p.y - p.h / 2).toBeGreaterThan(48);
    expect(p.y + p.h / 2).toBeLessThan(layout.height);
  }
  const rects = Array.from(layout.nodes.values());
  for (let i = 0; i < rects.length; i++)
    for (let j = i + 1; j < rects.length; j++) {
      const p = rects[i],
        q = rects[j];
      const overlap =
        Math.abs(p.x - q.x) < (p.w + q.w) / 2 &&
        Math.abs(p.y - q.y) < (p.h + q.h) / 2;
      if (overlap)
        throw new Error('Overlapping cards ' + p.id + ' and ' + q.id);
    }
  const again = layoutTopology(
    nodes.map((n) => ({ ...n, online: false })),
    paths.map((p) => ({ ...p, blocked: true })),
  );
  expect(Array.from(again.nodes.values(), (n) => [n.id, n.x, n.y])).toEqual(
    rects.map((n) => [n.id, n.x, n.y]),
  );
});

test('forward and reply use the same nodes with separate cubic paths and bounded marker progress', () => {
  const layout = layoutTopology(
    [node('a', 'tor', 0), node('b', 'provider', 1)],
    [],
  );
  const a = layout.nodes.get('a')!,
    b = layout.nodes.get('b')!;
  const forward = laneCurve(a, b, 'forward'),
    reply = laneCurve(b, a, 'reply');
  expect(onCurve(forward, 0)).toEqual(forward.start);
  expect(onCurve(reply, 1)).toEqual(reply.end);
  expect(onCurve(reply, 0.5).y).toBeGreaterThan(onCurve(forward, 0.5).y);
  expect(transitFraction(20, 10, 30)).toBe(0.5);
  expect(transitFraction(30, 10, 30)).toBeLessThan(1);
  expect(transitFraction(5, 10, 30)).toBeGreaterThan(0);
  expect(transitFraction(2, 2, 2)).toBe(0.5);
});

test('shows only the selected DHT node’s actual bucket contacts', () => {
  const dht = node('dht-1', 'dht', 2);
  const details = {
    node: dht,
    state: {
      buckets: [
        { contacts: [{ peer: 'dht-2' }, { peer: 'dht-4' }] },
        { contacts: [] },
      ],
    },
  } as unknown as NodeDetails;
  expect([...contactIds(details, 'dht-1')]).toEqual(['dht-2', 'dht-4']);
  expect(contactIds(details, 'dht-2').size).toBe(0);
  expect(contactIds(null, 'dht-1').size).toBe(0);
});
