import { expect, test } from 'vitest';
import {
  contactIds,
  extractRoute,
  makeTraceHistory,
  makeTrackRenderer,
  messageColour,
  packetRetryNotice,
  promoteJourney,
  transitEndpoints,
  laneCurve,
  layoutTopology,
  onCurve,
  transitFraction,
} from './graph-layout';
import type { LabEvent, LabNode, NodeDetails, Path } from './types';

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
  expect(
    Math.abs(layout.nodes.get('alice')!.y - layout.height / 2),
  ).toBeLessThanOrEqual(4);
  expect(layout.stages.map((s) => s.index)).toEqual([1, 2, 3, 4, 5, 6]);
  expect(
    layout.groups.map((group) => [group.name, group.stageIndices]),
  ).toEqual([
    ['Loopix', [2, 3, 4]],
    ['DHT', [5]],
  ]);
  for (const group of layout.groups) {
    const members = layout.stages.filter((stage) =>
      group.stageIndices.includes(stage.index),
    );
    expect(group.x).toBeLessThan(members[0].x);
    expect(group.x + group.width).toBeGreaterThan(
      members.at(-1)!.x + members.at(-1)!.width,
    );
  }
  for (const n of nodes.filter((n) => n.kind !== 'person')) {
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

test('promotes every leg of the selected message journey as one stable chain', () => {
  const tracks = [
    { id: 'first', messageId: 'msg-1' },
    { id: 'chosen-a', messageId: 'msg-2' },
    { id: 'third', messageId: 'msg-3' },
    { id: 'chosen-b', messageId: 'msg-2' },
  ];
  expect(promoteJourney(tracks, 'msg-2').map((track) => track.id)).toEqual([
    'first',
    'third',
    'chosen-a',
    'chosen-b',
  ]);
  expect(promoteJourney(tracks)).toBe(tracks);
});

test('anchors participants at the chat edges, centred and stacked, with routed avatar ports', () => {
  const layout = layoutTopology(
    [
      node('alice', 'person', 0),
      node('carol', 'person', 0),
      node('west', 'tor', 1),
      node('east', 'direct', 9),
      node('bob', 'person', 10),
    ],
    [path('alice', 'west'), path('carol', 'west'), path('bob', 'east')],
    { width: 1024, height: 480 },
  );
  const alice = layout.nodes.get('alice')!,
    carol = layout.nodes.get('carol')!,
    bob = layout.nodes.get('bob')!;
  expect(alice.x).toBe(carol.x);
  expect((alice.y + carol.y) / 2).toBeCloseTo(layout.height / 2, 0);
  expect(carol.y - alice.y).toBe(72);
  expect(bob.y).toBeCloseTo(layout.height / 2, 0);
  expect(alice.x + alice.w / 2).toBeLessThan(layout.stages[0].x);
  expect(bob.x - bob.w / 2).toBeGreaterThan(
    layout.stages[1].x + layout.stages[1].width,
  );
  const west = layout.nodes.get('west')!;
  expect([west.w, west.h]).toEqual([34, 24]);
  for (const offset of [0, 10, -20]) {
    const start = laneCurve(alice, west, 'forward', offset).start;
    expect(Math.hypot(start.x - alice.x, start.y - alice.y)).toBeCloseTo(
      alice.w / 2,
    );
    const end = laneCurve(west, alice, 'reply', offset).end;
    expect(Math.hypot(end.x - alice.x, end.y - alice.y)).toBeCloseTo(
      alice.w / 2,
    );
  }
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

test('extracts the exact reported route with its lane, repeats and retry attempt', () => {
  const event: LabEvent = {
    event_type: 'mixnet_route_constructed',
    event_id: 'evt-13',
    sequence: 13,
    simulation_time_ms: 80,
    simulation_id: 'lab-1',
    step_id: 'step-4',
    source_id: 'sender-1',
    target_id: 'west',
    message_id: 'msg-2',
    conversation_id: 'conversation-1',
    payload: {
      packet_id: 'pkt-7',
      attempt: 2,
      lane: 'reply',
      ordered_route: ['west', 'mix-2', 'west'],
    },
  };
  const route = extractRoute(event)!;
  expect(route.nodes).toEqual(['west', 'mix-2', 'west']);
  expect(route.legs).toEqual([
    { id: 'mix-2~west', source: 'west', target: 'mix-2', lane: 'reply' },
    { id: 'mix-2~west', source: 'mix-2', target: 'west', lane: 'reply' },
  ]);
  expect(route.retry).toBe(true);
  expect(
    extractRoute({ ...event, event_type: 'path_transit_completed' }),
  ).toBeNull();
  expect(
    extractRoute({
      ...event,
      payload: { ...event.payload, ordered_route: ['west', null, 'east'] },
    }),
  ).toBeNull();
  const history = makeTraceHistory();
  expect(history('first', [event]).retries.has('pkt-7')).toBe(true);
  expect(history('reset', []).retries.size).toBe(0);
});

test('explains that a failed Sphinx route stops before a fresh sender retry', () => {
  const base: LabEvent = {
    event_type: 'message_forward_failed',
    event_id: 'evt-1',
    sequence: 1,
    simulation_time_ms: 20,
    simulation_id: 'lab-1',
    step_id: 'step-1',
    source_id: 'mix-1',
    target_id: 'mix-2',
    message_id: 'msg-1',
    conversation_id: 'conversation-1',
    payload: { packet_id: 'packet-1', attempt: 1 },
  };
  expect(packetRetryNotice([base])).toContain(
    'sender will create a fresh end-to-end attempt',
  );
  expect(
    packetRetryNotice([
      base,
      {
        ...base,
        sequence: 2,
        event_type: 'packet_retry_scheduled',
        payload: {
          packet_id: 'packet-2',
          previous_packet_id: 'packet-1',
          attempt: 2,
        },
      },
    ]),
  ).toContain('queued for the sender’s next payload opportunity');
  expect(
    packetRetryNotice([
      base,
      {
        ...base,
        sequence: 3,
        event_type: 'mixnet_route_constructed',
        payload: { packet_id: 'packet-2', attempt: 2 },
      },
    ]),
  ).toBe(
    'Retry packet-2 is now using a newly selected end-to-end route (attempt 2).',
  );
  expect(packetRetryNotice([{ ...base, message_id: null }])).toBeNull();
});

test('counts actual sources, destinations and retries independently at shared nodes', () => {
  const base = { start_ms: 1, end_ms: 9, lane: 'forward' as const };
  const rows = transitEndpoints(
    [
      { ...base, source: 'A', target: 'B', token: 'pkt-1' },
      { ...base, source: 'B', target: 'A', token: 'pkt-2', lane: 'reply' },
      { ...base, source: 'C', target: 'B', token: 'pkt-3' },
    ],
    new Set(['pkt-2']),
  );
  expect(rows.get('B')).toEqual({
    outgoing: 1,
    incoming: 2,
    outgoingRetries: 1,
    incomingRetries: 0,
  });
  expect(rows.get('A')).toEqual({
    outgoing: 1,
    incoming: 1,
    outgoingRetries: 0,
    incomingRetries: 1,
  });
  expect(rows.has('D')).toBe(false);
});

test('retains message-associated device, reply and repeat transits with their authoritative cargo and timing', () => {
  const log: LabEvent[] = [];
  function record(
    kind: string,
    id: string,
    messageId: string | null,
    lane: 'reply' | 'forward',
    time: number,
    extra: LabEvent['payload'] = {},
  ) {
    const n = log.length + 1;
    log.push({
      event_id: 'evt-' + n,
      step_id: null,
      sequence: n,
      simulation_id: 'lab',
      event_type: 'path_transit_' + kind,
      simulation_time_ms: time,
      message_id: messageId,
      conversation_id: null,
      source_id: lane === 'reply' ? 'tor-alice' : 'alice',
      target_id: lane === 'reply' ? 'alice' : 'tor-alice',
      payload: {
        transit_id: id,
        path_id: 'alice~tor-alice',
        lane,
        token: 'cell-' + id,
        ...extra,
      },
    });
  }
  const history = makeTraceHistory();
  record('started', 'one', 'msg-1', 'forward', 3, {
    cargo: { bytes: 64, digest: '01' },
    end_ms: 14,
  });
  const started = history('lab:0', log).legs.get('one')!;
  expect(started).toMatchObject({
    source: 'alice',
    target: 'tor-alice',
    status: 'active',
    startMs: 3,
    endMs: null,
  });
  record('completed', 'one', 'msg-1', 'forward', 14);
  record('started', 'second', 'msg-2', 'reply', 15);
  record('completed', 'second', 'msg-2', 'reply', 22);
  record('failed', 'three', 'msg-1', 'forward', 28, { reason: 'blocked' });
  record('started', 'maintenance', null, 'forward', 29);
  record('started', 'four', 'msg-3', 'forward', 30);
  record('failed', 'bootstrap', null, 'forward', 31);
  const data = history('lab:0', log);
  expect(data.legs.get('one')).toMatchObject({
    status: 'completed',
    startMs: 3,
    endMs: 14,
    expectedEndMs: 14,
    cargo: { bytes: 64, digest: '01' },
  });
  expect(data.legs.get('three')).toMatchObject({
    status: 'failed',
    startMs: null,
    endMs: 28,
    reason: 'blocked',
    cargo: {},
  });
  expect(data.legs.get('second')).toMatchObject({
    source: 'tor-alice',
    target: 'alice',
    lane: 'reply',
  });
  expect(data.legs.has('maintenance')).toBe(false);
  expect(data.seen.get('alice~tor-alice')?.failed).toBe(true);
  expect(data.seenMessages.get('alice~tor-alice')?.failed).toBe(false);
  const [first, reply, other] = data.messageTracks.values();
  expect(first.legs).toEqual(['one', 'three']);
  expect(reply.lane).toBe('reply');
  expect(other.offset).not.toBe(first.offset);
  const layout = layoutTopology(
    [node('alice', 'person', 0), node('tor-alice', 'tor', 1)],
    [],
  );
  const { nodes } = layout;
  const renderTrack = makeTrackRenderer(layout);
  const rendered = renderTrack(first, started);
  expect(renderTrack(first, started)).toBe(rendered);
  expect(renderTrack(first, data.legs.get('one')!)?.latest.status).toBe(
    'completed',
  );
  const curve = (offset: number) =>
    laneCurve(nodes.get('alice')!, nodes.get('tor-alice')!, 'forward', offset);
  expect(onCurve(curve(first.offset), 0.5)).not.toEqual(
    onCurve(curve(other.offset), 0.5),
  );
  expect(
    new Set(
      Array.from({ length: 64 }, (_, i) => messageColour('msg-' + (i + 1))),
    ).size,
  ).toBe(64);
  expect(history('lab:1', []).legs.size).toBe(0);
});

test('same-epoch sliding, replayed and backfilled event windows retain completed source legs', () => {
  const history = makeTraceHistory();
  function hop(
    sequence: number,
    src: string,
    dst: string,
    id: string,
    phase: string,
  ): LabEvent {
    return {
      sequence,
      event_id: 'event-' + sequence,
      simulation_id: 'one',
      step_id: null,
      simulation_time_ms: sequence,
      source_id: src,
      target_id: dst,
      message_id: 'msg-1',
      conversation_id: null,
      event_type: 'path_transit_' + phase,
      payload: {
        token: 'pkt-1',
        path_id: [src, dst].sort().join('~'),
        transit_id: id,
        lane: 'forward',
        ...(phase === 'started' ? { cargo: { bytes: 512 } } : {}),
      },
    };
  }
  const rows = [
    hop(10, 'Alice', 'Tor', 'first', 'started'),
    hop(11, 'Alice', 'Tor', 'first', 'completed'),
    hop(12, 'Tor', 'Ingress', 'next', 'started'),
    hop(13, 'Tor', 'Ingress', 'next', 'completed'),
  ];
  history('run', rows.slice(0, 2));
  history('run', rows.slice(1, 3)); // Same-length sliding window
  expect(history('run', rows.slice(3)).legs.get('first')).toMatchObject({
    status: 'completed',
    cargo: { bytes: 512 },
    startMs: 10,
  });
  expect(history('run', rows).legs.size).toBe(2);
  const mountedLate = makeTraceHistory();
  mountedLate('run', rows.slice(1)); // completion but no departure in the partial snapshot
  expect(mountedLate('run', rows).legs.get('first')).toMatchObject({
    status: 'completed',
    cargo: { bytes: 512 },
    startMs: 10,
  });
  expect(history('reset', []).legs.size).toBe(0);
});
