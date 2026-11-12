import { writable, type Readable } from 'svelte/store';
import type {
  ClientState,
  CommandArgs,
  CommandType,
  Config,
  Delta,
  Json,
  LabEvent,
  NodeDetails,
  Snapshot,
} from './types';

const blank = (): ClientState => ({
  connection: 'disconnected',
  http: '',
  ws: '',
  version: '',
  error: '',
  config: null,
  snapshot: null,
  events: [],
  pending: 0,
  feedback: '',
});
const reason = (err: unknown) =>
  err instanceof Error ? err.message : String(err);
const backoff = [250, 500, 1000, 2000, 4000];
type Reply = Record<string, Json>;
class BackendRejection extends Error {}
type Frame =
  | { type: 'backend_ready'; api_version: string }
  | {
      type: 'snapshot';
      state: Snapshot;
      history_after: number;
      events: LabEvent[];
    }
  | { type: 'delta'; delta: Delta }
  | { type: 'ack' | 'pong'; command_id: string; result?: Reply }
  | { type: 'error'; command_id: string | null; detail: string };
interface Health {
  status: string;
  service: string;
  api_version: string;
  simulation_id: string | null;
}
interface Waiter {
  resolve: (result: Reply) => void;
  reject: (error: Error) => void;
  timer: ReturnType<typeof setTimeout>;
}

export function resolveEndpoint(input: string): { http: string; ws: string } {
  const text = input.trim();
  if (!text)
    throw new Error('Enter the port or local HTTP endpoint printed by Python.');
  let url: URL;
  if (/^\d+$/.test(text)) {
    if (+text < 1 || +text > 65535)
      throw new Error('Enter a port from 1 to 65535.');
    url = new URL('http://127.0.0.1:' + text);
  } else {
    try {
      url = new URL(text);
    } catch {
      throw new Error('Enter a port or a complete local HTTP URL.');
    }
  }
  if (
    !['http:', 'https:'].includes(url.protocol) ||
    !['localhost', '127.0.0.1', '[::1]'].includes(url.hostname) ||
    url.username ||
    url.password ||
    url.search ||
    url.hash ||
    url.port === '0'
  ) {
    throw new Error(
      'Use a local HTTP or HTTPS endpoint without credentials, query parameters or a fragment.',
    );
  }
  const http = url.href.replace(/\/+$/, '');
  return { http, ws: http.replace(/^http/, 'ws') + '/ws' };
}
async function json<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...options,
    signal: AbortSignal.timeout(12000),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const message =
      typeof body?.detail === 'string'
        ? body.detail
        : Array.isArray(body?.detail)
          ? body.detail
              .map((e: { loc?: string[]; msg?: string }) =>
                [e.loc?.slice(1).join('.'), e.msg].filter(Boolean).join(' — '),
              )
              .join('; ')
          : '';
    throw new Error(message || 'Backend returned HTTP ' + response.status);
  }
  return response.json();
}
function replace<T extends { id: string }>(rows: T[], changes: T[]): T[] {
  if (!changes.length) return rows;
  const byId = new Map(changes.map((row) => [row.id, row]));
  const next = rows.map((row) => {
    const change = byId.get(row.id);
    byId.delete(row.id);
    return change ?? row;
  });
  return [...next, ...byId.values()];
}
export function applyDelta(s: Snapshot, d: Delta): Snapshot {
  return {
    ...s,
    status: d.status,
    sequence: d.sequence,
    simulation_time_ms: d.simulation_time_ms,
    next_step_ms: d.next_step_ms,
    first_message_hop_sequence: d.first_message_hop_sequence,
    step_delay_ms: d.step_delay_ms,
    initialised: d.initialised,
    topology:
      !d.nodes.length && !d.paths.length
        ? s.topology
        : {
            nodes: replace(s.topology.nodes, d.nodes),
            paths: replace(s.topology.paths, d.paths),
          },
    devices: replace(s.devices, d.devices),
    messages: replace(s.messages, d.messages),
    outcomes: { ...s.outcomes, ...d.outcomes },
    lineage: d.lineage.length ? s.lineage.concat(d.lineage) : s.lineage,
  };
}

export class LabClient {
  private state = blank();
  private readonly writable = writable<ClientState>(this.state);
  readonly store: Readable<ClientState> = {
    subscribe: this.writable.subscribe,
  };
  private socket: WebSocket | null = null;
  private generation = 0;
  private activeId: string | null = null;
  private subscription = '';
  private ready = '';
  private retryTimer: ReturnType<typeof setTimeout> | undefined;
  private attempt = 0;
  private waiters = new Map<string, Waiter>();
  private set(partial: Partial<ClientState>) {
    this.state = { ...this.state, ...partial };
    this.writable.set(this.state);
  }
  private span(id: string, timeout = 15000): Promise<Reply> {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(
        () =>
          this.settle(
            id,
            new Error('The backend did not confirm this request in time.'),
          ),
        timeout,
      );
      this.waiters.set(id, { resolve, reject, timer });
      this.set({ pending: this.waiters.size });
    });
  }
  private settle(id: string, value: Error | Reply) {
    const waiter = this.waiters.get(id);
    if (!waiter) return;
    clearTimeout(waiter.timer);
    this.waiters.delete(id);
    this.set({ pending: this.waiters.size });
    if (value instanceof Error) waiter.reject(value);
    else waiter.resolve(value);
  }
  private clearSocket() {
    const socket = this.socket;
    this.socket = null;
    if (socket) {
      socket.onclose = null;
      socket.onerror = null;
      socket.onmessage = null;
      socket.close();
    }
    for (const id of this.waiters.keys())
      this.settle(
        id,
        new Error(
          'Connection closed before the backend confirmed the request.',
        ),
      );
    this.subscription = '';
    this.ready = '';
  }
  disconnect() {
    this.generation++;
    clearTimeout(this.retryTimer);
    this.clearSocket();
    this.activeId = null;
    this.attempt = 0;
    this.set({ ...blank(), http: this.state.http, ws: this.state.ws });
  }
  async test(input: string): Promise<void> {
    this.disconnect();
    const generation = this.generation;
    this.set({ connection: 'testing', http: '', ws: '' });
    try {
      const endpoint = resolveEndpoint(input);
      this.set(endpoint);
      const health = await this.health(endpoint.http);
      if (generation === this.generation)
        this.set({ connection: 'tested', version: health.api_version });
    } catch (err) {
      if (generation === this.generation) {
        this.set({ connection: 'error', error: reason(err) });
        throw err;
      }
    }
  }
  private async health(http: string): Promise<Health> {
    const health = await json<Health>(http + '/health');
    if (health.status !== 'ok' || health.service !== 'simulation-backend')
      throw new Error(
        'The endpoint did not identify a healthy simulation backend.',
      );
    return health;
  }
  async connect(): Promise<void> {
    if (this.state.connection !== 'tested')
      throw new Error('Test the backend endpoint before connecting.');
    this.attempt = 0;
    await this.open(false);
  }
  private async open(retry: boolean) {
    const generation = ++this.generation;
    this.set({ connection: retry ? 'reconnecting' : 'connecting', error: '' });
    try {
      const [health, config] = await Promise.all([
        this.health(this.state.http),
        json<Config>(this.state.http + '/api/config'),
      ]);
      if (generation !== this.generation) return;
      // A running server can own multiple labs. Keep the selected lab on reconnect.
      let selected = health.simulation_id;
      if (retry && this.activeId && selected && this.activeId !== selected) {
        const prior = await fetch(
          this.state.http +
            '/api/simulations/' +
            encodeURIComponent(this.activeId),
          { signal: AbortSignal.timeout(12000) },
        );
        if (generation !== this.generation) return;
        if (prior.ok) selected = this.activeId;
        else if (prior.status !== 404)
          throw new Error('Could not recover the selected simulation.');
      }
      this.activeId = selected;
      if (!this.activeId) this.set({ snapshot: null, events: [] });
      this.set({ version: health.api_version, config });
      const socket = new WebSocket(this.state.ws);
      this.socket = socket;
      this.ready = crypto.randomUUID();
      const connected = this.span(this.ready, 20000);
      let incoming = Promise.resolve();
      socket.onmessage = (e) => {
        incoming = incoming
          .then(async () => {
            if (this.socket === socket)
              await this.receive(JSON.parse(e.data) as Frame, socket);
          })
          .catch((err) => {
            if (this.socket === socket) {
              this.set({ error: reason(err) });
              socket.close();
            }
          });
      };
      socket.onerror = () => socket.close();
      socket.onclose = () => {
        if (this.socket !== socket) return;
        const established = this.state.connection === 'connected';
        this.clearSocket();
        if (established) this.reconnect();
      };
      await connected;
      if (this.socket === socket) {
        this.attempt = 0;
        this.set({ connection: 'connected', error: '' });
      }
    } catch (err) {
      if (generation !== this.generation) return;
      this.clearSocket();
      if (retry) this.reconnect(reason(err));
      else {
        this.set({ connection: 'error', error: reason(err) });
        throw err;
      }
    }
  }
  private reconnect(error = 'Connection lost. Reconnecting to Python…') {
    const delay = backoff[this.attempt++];
    if (delay === undefined) {
      this.set({
        connection: 'error',
        error: 'Could not reconnect. Test the endpoint again.',
      });
      return;
    }
    this.set({ connection: 'reconnecting', error });
    clearTimeout(this.retryTimer);
    this.retryTimer = setTimeout(() => {
      void this.open(true);
    }, delay);
  }
  private subscribe(wait = true) {
    if (!this.socket || !this.activeId)
      throw new Error('No simulation available to subscribe to.');
    const id = crypto.randomUUID();
    this.subscription = id;
    const old = this.state.snapshot;
    const known = old?.simulation_id === this.activeId ? old : null;
    const promise = wait ? this.span(id, 30000) : Promise.resolve({});
    this.socket.send(
      JSON.stringify({
        type: 'subscribe',
        command_id: id,
        simulation_id: this.activeId,
        epoch: known?.epoch ?? null,
        after_sequence: known?.sequence ?? 0,
      }),
    );
    return promise;
  }
  private async receive(frame: Frame, socket: WebSocket) {
    if (frame.type === 'backend_ready') {
      if (this.activeId) this.subscribe(false);
      else this.settle(this.ready, {});
      return;
    }
    if (frame.type === 'error') {
      this.set({ error: frame.detail, feedback: 'Command rejected' });
      if (frame.command_id)
        this.settle(frame.command_id, new BackendRejection(frame.detail));
      if (frame.command_id === this.subscription)
        this.settle(this.ready, new Error(frame.detail));
      return;
    }
    if (frame.type === 'ack' || frame.type === 'pong') {
      this.set({ feedback: 'Command applied', error: '' });
      this.settle(frame.command_id, frame.result ?? {});
      return;
    }
    if (frame.type === 'snapshot') {
      const s = frame.state;
      if (s.simulation_id !== this.activeId) return;
      const previous = this.state.snapshot;
      const same =
        s.simulation_id === previous?.simulation_id &&
        previous.epoch === s.epoch &&
        previous.sequence <= s.sequence;
      let history = same ? this.state.events.slice() : [];
      let last = history.at(-1)?.sequence ?? 0;
      while (last < frame.history_after) {
        const query =
          '/events?after=' +
          last +
          '&limit=' +
          Math.min(5000, frame.history_after - last);
        const page = await json<{ epoch: number; events: LabEvent[] }>(
          this.state.http +
            '/api/simulations/' +
            encodeURIComponent(s.simulation_id) +
            query,
        );
        if (this.socket !== socket || s.simulation_id !== this.activeId) return;
        if (page.epoch !== s.epoch) {
          this.subscribe(false);
          return;
        }
        if (!page.events.length || page.events[0].sequence !== last + 1)
          throw new Error('Could not recover missing simulation events.');
        history.push(...page.events);
        last = page.events[page.events.length - 1].sequence;
      }
      history = history.concat(frame.events.filter((e) => e.sequence > last));
      this.set({ snapshot: s, events: history, error: '' });
      this.settle(this.subscription, {});
      this.settle(this.ready, {});
      return;
    }
    if (frame.type === 'delta') {
      const d = frame.delta,
        s = this.state.snapshot;
      if (d.simulation_id !== this.activeId) return;
      if (
        !s ||
        s.simulation_id !== d.simulation_id ||
        d.epoch !== s.epoch ||
        (d.sequence > s.sequence && d.events[0]?.sequence !== s.sequence + 1)
      ) {
        this.subscribe(false);
        return;
      }
      if (d.sequence > s.sequence)
        this.set({
          snapshot: applyDelta(s, d),
          events: this.state.events.concat(d.events),
        });
    }
  }
  async create(config: Config): Promise<void> {
    if (this.state.connection !== 'connected')
      throw new Error('Connect before creating a simulation.');
    const generation = this.generation;
    this.set({ pending: this.state.pending + 1, error: '', feedback: '' });
    try {
      const state = await json<Snapshot>(this.state.http + '/api/simulations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      });
      if (
        this.generation !== generation ||
        this.state.connection !== 'connected'
      )
        throw new Error('Connection changed while creating the simulation.');
      this.activeId = state.simulation_id;
      await this.subscribe();
      this.set({ feedback: 'Simulation created' });
    } catch (err) {
      if (generation === this.generation) this.set({ error: reason(err) });
      throw err;
    } finally {
      if (generation === this.generation)
        this.set({ pending: this.waiters.size });
    }
  }
  async command(type: CommandType, extra: CommandArgs = {}): Promise<Reply> {
    const s = this.state.snapshot;
    if (!s || this.state.connection !== 'connected' || !this.socket)
      throw new Error('Connect to a simulation before sending commands.');
    const id = crypto.randomUUID();
    const response = this.span(id);
    this.set({ feedback: 'Command pending', error: '' });
    try {
      this.socket.send(
        JSON.stringify({
          ...extra,
          type,
          command_id: id,
          simulation_id: s.simulation_id,
          epoch: s.epoch,
        }),
      );
    } catch (err) {
      this.settle(id, new Error(reason(err)));
    }
    try {
      return await response;
    } catch (err) {
      this.set({
        feedback:
          err instanceof BackendRejection
            ? 'Command rejected'
            : 'Command unconfirmed',
        error: reason(err),
      });
      throw err;
    }
  }
  async inspect(nodeId: string): Promise<NodeDetails> {
    const s = this.state.snapshot;
    if (!s) throw new Error('Create a simulation before inspecting a node.');
    return json<NodeDetails>(
      this.state.http +
        '/api/simulations/' +
        encodeURIComponent(s.simulation_id) +
        '/nodes/' +
        encodeURIComponent(nodeId),
    );
  }
}
