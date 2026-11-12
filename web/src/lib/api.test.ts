import { get } from 'svelte/store';
import { afterEach, expect, test, vi } from 'vitest';
import { findUpdatedBackend, LabClient, resolveEndpoint } from './api';
import type { Config, Delta, LabEvent, Snapshot } from './types';

const event = (n: number): LabEvent => ({
  event_id: 'e' + n,
  event_type: 'test',
  sequence: n,
  simulation_id: 'sim',
  simulation_time_ms: n,
  step_id: null,
  source_id: null,
  target_id: null,
  message_id: null,
  conversation_id: null,
  payload: {},
});
const snapshot: Snapshot = {
  simulation_id: 'sim',
  random_seed: 1,
  epoch: 0,
  sequence: 0,
  status: 'ready',
  step_delay_ms: 500,
  next_step_ms: null,
  first_message_hop_sequence: null,
  simulation_time_ms: 0,
  initialised: false,
  config: {} as Config,
  topology: { nodes: [], paths: [] },
  profiles: [],
  observer: { id: 'observer', lifecycle: 'created' },
  devices: [],
  messages: [
    {
      id: 'm',
      conversation_id: 'c',
      exchange: 1,
      sender_id: 'a',
      target_id: 'b',
      direction: 'forward',
      text: 'secret',
    },
  ],
  lineage: [],
  outcomes: {},
};
function update(sequence: number): Delta {
  return {
    simulation_id: 'sim',
    epoch: 0,
    sequence,
    status: 'running',
    initialised: true,
    step_delay_ms: 500,
    simulation_time_ms: sequence,
    next_step_ms: 10,
    first_message_hop_sequence: null,
    nodes: [],
    paths: [],
    lineage: [],
    devices: [],
    outcomes: { m: 'sent' },
    messages: [{ ...snapshot.messages[0], text: null }],
    events: [event(sequence)],
  };
}
class MockSocket {
  static latest: MockSocket;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  sent: Record<string, unknown>[] = [];
  constructor() {
    MockSocket.latest = this;
    queueMicrotask(() =>
      this.frame({ type: 'backend_ready', api_version: '1' }),
    );
  }
  frame(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }
  send(data: string) {
    this.sent.push(JSON.parse(data));
  }
  close() {
    this.onclose?.();
  }
}
const flush = async () => {
  for (let i = 0; i < 20; i++) await Promise.resolve();
};
function backend(sid: string | null = null) {
  vi.stubGlobal('WebSocket', MockSocket);
  const request = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith('/health'))
      return Response.json({
        status: 'ok',
        service: 'simulation-backend',
        api_version: '1',
        simulation_id: sid,
      });
    if (url.endsWith('/api/config')) return Response.json(snapshot.config);
    if (url.endsWith('/api/simulations') && init?.method === 'POST')
      return Response.json(snapshot);
    if (url.includes('/events?after=0'))
      return Response.json({ epoch: 0, events: [event(1), event(2)] });
    return Response.json({ detail: 'Unknown test request' }, { status: 404 });
  });
  vi.stubGlobal('fetch', request);
  return request;
}
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});
test('resolves local ports, full endpoints and secure WebSockets', () => {
  expect(resolveEndpoint(' 8205 ')).toEqual({
    http: 'http://127.0.0.1:8205',
    ws: 'ws://127.0.0.1:8205/ws',
  });
  expect(resolveEndpoint('https://localhost:4443/lab/').ws).toBe(
    'wss://localhost:4443/lab/ws',
  );
  for (const bad of [
    '',
    '0',
    '65536',
    'ws://localhost:4',
    'file:///tmp/lab',
    'https://example.org',
    'https://user@localhost',
    'http://localhost/?token=one',
  ])
    expect(() => resolveEndpoint(bad)).toThrow();
});
test('a failed health check leaves the endpoint editable and no WebSocket connection', async () => {
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValue(
        Response.json({ detail: 'Python unavailable' }, { status: 503 }),
      ),
  );
  const client = new LabClient();
  await expect(client.test('9001')).rejects.toThrow('Python unavailable');
  expect(get(client.store)).toMatchObject({
    connection: 'error',
    http: 'http://127.0.0.1:9001',
    snapshot: null,
  });
  backend();
  await client.test('9002');
  expect(get(client.store).connection).toBe('tested');
  client.disconnect();
});
test('connect and create are separate, creation waits for a snapshot, deltas replace redacted records', async () => {
  const request = backend();
  const client = new LabClient();
  await client.test('9211');
  await client.connect();
  expect(get(client.store)).toMatchObject({
    connection: 'connected',
    snapshot: null,
    pending: 0,
  });
  expect(request.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(
    false,
  );
  const creating = client.create(snapshot.config);
  await flush();
  const socket = MockSocket.latest;
  expect(socket.sent.at(-1)).toMatchObject({
    type: 'subscribe',
    simulation_id: 'sim',
  });
  expect(get(client.store).snapshot).toBeNull();
  socket.frame({
    type: 'snapshot',
    state: snapshot,
    history_after: 0,
    events: [],
  });
  await creating;
  const command = client.command('run');
  const id = socket.sent.at(-1)?.command_id;
  expect(get(client.store).pending).toBe(1);
  socket.frame({ type: 'ack', command_id: id, result: { status: 'running' } });
  await expect(command).resolves.toEqual({ status: 'running' });
  socket.frame({ type: 'delta', delta: update(1) });
  await flush();
  expect(get(client.store).snapshot?.messages[0].text).toBeNull();
  expect(get(client.store).events.map((e) => e.sequence)).toEqual([1]);
  const rejected = client.command('resume');
  socket.frame({
    type: 'error',
    command_id: socket.sent.at(-1)?.command_id,
    detail: 'Cannot resume',
  });
  await expect(rejected).rejects.toThrow('Cannot resume');
  expect(get(client.store)).toMatchObject({
    pending: 0,
    error: 'Cannot resume',
    feedback: 'Command rejected',
  });
  client.disconnect();
  expect(get(client.store)).toMatchObject({
    snapshot: null,
    events: [],
    connection: 'disconnected',
  });
});
test('refresh discovers current run, backfills truncated history and reconnects after the cursor', async () => {
  vi.useFakeTimers();
  backend('sim');
  const client = new LabClient();
  await client.test('9212');
  const opening = client.connect();
  await flush();
  const socket = MockSocket.latest;
  expect(socket.sent.at(-1)).toMatchObject({
    type: 'subscribe',
    after_sequence: 0,
  });
  socket.frame({
    type: 'snapshot',
    state: { ...snapshot, sequence: 3 },
    history_after: 2,
    events: [event(3)],
  });
  await opening;
  expect(get(client.store).events.map((e) => e.sequence)).toEqual([1, 2, 3]);
  socket.close();
  expect(get(client.store).connection).toBe('reconnecting');
  await vi.advanceTimersByTimeAsync(250);
  await flush();
  const next = MockSocket.latest;
  expect(next).not.toBe(socket);
  expect(next.sent.at(-1)).toMatchObject({
    type: 'subscribe',
    epoch: 0,
    after_sequence: 3,
  });
  next.frame({
    type: 'snapshot',
    state: { ...snapshot, sequence: 4 },
    history_after: 3,
    events: [event(4)],
  });
  await flush();
  expect(get(client.store).events.map((e) => e.sequence)).toEqual([1, 2, 3, 4]);
  expect(get(client.store).connection).toBe('connected');
  next.frame({
    type: 'snapshot',
    state: { ...snapshot, epoch: 1 },
    history_after: 0,
    events: [],
  });
  await flush();
  expect(get(client.store).events).toEqual([]);
  client.disconnect();
});

test('discovery skips the connected server and rejects incomplete or unrelated services', async () => {
  const probes = vi.fn(async (url: string) => {
    const { port, pathname } = new URL(url);
    if (pathname === '/health')
      return Response.json({
        status: 'ok',
        service: port === '8000' ? 'other' : 'simulation-backend',
        first_departure_playback: port !== '8001',
      });
    if (pathname === '/api/config')
      return Response.json({ sender_channel: 'tor', recipient_channel: 'tor' });
    return Response.json({
      protocols: port === '8004' ? [{ id: 'anonymous-retrieval' }] : [],
    });
  });
  vi.stubGlobal('fetch', probes);
  await expect(findUpdatedBackend('http://127.0.0.1:8002')).resolves.toBe(
    'http://127.0.0.1:8004',
  );
  expect(probes.mock.calls.some(([url]) => url.includes(':8002/'))).toBe(false);
  expect(probes.mock.calls.some(([url]) => url.includes(':8000/api/'))).toBe(
    false,
  );
});
