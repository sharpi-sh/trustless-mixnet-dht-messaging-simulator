export type Json =
  string | number | boolean | null | Json[] | { [key: string]: Json };
export type Channel = 'tor' | 'shadowsocks' | 'direct';
export type Direction = 'forward' | 'reply';
export type Status =
  'ready' | 'running' | 'paused' | 'stopped' | 'completed' | 'failed';
export type Outcome = 'staged' | 'sent' | 'received' | 'failed' | 'skipped';
export interface Outage {
  node_id: string;
  start_ms: number;
  duration_ms: number;
}
export interface Config {
  sender_channel?: Channel;
  recipient_channel?: Channel;
  sender_count: number;
  receiver_count: number;
  min_nodes: number;
  max_nodes: number;
  randomise_count: boolean;
  pairing_strategy:
    'all_to_one' | 'one_to_all' | 'one_to_one_pairs' | 'random_pairs';
  pair_count: number;
  exchanges: number;
  random_seed: number | null;
  polling_enabled: boolean;
  polling_overrides: Record<string, boolean>;
  polling_interval_ms: number;
  poll_batch: number;
  base_transit_delay_ms: number;
  jitter_min_ms: number;
  jitter_max_ms: number;
  mu_per_second: number;
  payload_rate_per_minute: number;
  client_loop_rate_per_minute: number;
  drop_cover_rate_per_minute: number;
  mix_loop_rate_per_minute: number;
  dht_nodes: number;
  storage_nodes: number;
  replicas: number;
  chunk_bytes: number;
  pattern:
    'always_online' | 'always_offline' | 'random' | 'bursty' | 'scheduled';
  failure_probability: number;
  min_outage_ms: number;
  max_outage_ms: number;
  min_online_ms: number;
  initial_offline_probability: number;
  always_offline_probability: number;
  always_online_probability: number;
  scheduled_outages: Outage[];
  operator_count: number;
  max_retries: number;
  ack_timeout_ms: number;
  step_delay_ms: number;
}
export interface Observation {
  peer_id: string;
  status: 'unknown' | 'online' | 'unresponsive';
  last_contact: number | null;
  last_failure: number | null;
  failures: number;
  successes: number;
}
export interface LabNode {
  id: string;
  label: string;
  kind: 'person' | Channel | 'provider' | 'mix' | 'dht' | 'storage';
  stage_index: number;
  stage: string;
  simulated_address: string;
  egress_address?: string | null;
  operator_id: string;
  online: boolean;
  history: [number, boolean][];
  last_activity: number | null;
  failure_count: number;
  adjacent_peers?: Record<string, Observation>;
  delayed_packets?: Record<string, number>;
}
export interface ActiveTransit {
  start_ms: number;
  end_ms: number;
  source: string;
  target: string;
  lane: Direction;
  token: string;
}
export interface IPHop {
  source_ip: string;
  destination_ip: string;
  observed_source_ip: string;
  observer: string;
  description: string;
  local: boolean;
}
export interface Path {
  ip_hops?: Record<string, IPHop>;
  local?: boolean;
  id: string;
  source_id: string;
  target_id: string;
  boundary: string;
  transport_label: string;
  base_transit_delay_ms: number;
  jitter_min_ms: number;
  jitter_max_ms: number;
  blocked: boolean;
  blocked_at: number | null;
  blocked_by: string | null;
  active: Record<string, ActiveTransit>;
  attempted: number;
  completed: number;
  failed: number;
  dropped: number;
}
export interface DeviceLog {
  message_id: string;
  conversation_id: string;
  direction: Direction;
  state: 'staged' | 'sent' | 'delivered' | 'received' | 'replied' | 'failed';
  verified_signer_id?: string | null;
  signing_fingerprint?: string | null;
  simulation_time_ms: number;
  text: string;
}
export interface Device {
  id: string;
  label: string;
  role: 'sender' | 'receiver';
  tor_id: string;
  channel?: Channel;
  channel_id?: string;
  fingerprint: string;
  signing_fingerprint?: string | null;
  polling_enabled: boolean;
  logs: DeviceLog[];
}
export interface Message {
  id: string;
  conversation_id: string;
  sender_id: string;
  target_id: string;
  exchange: number;
  direction: Direction;
  text?: string | null;
}
export interface Profile {
  id: string;
  name: string;
  year: number | null;
  reference: string | null;
  parameters: Record<string, Json>;
  operations: string[];
  boundaries: string[];
}
export interface NodeDetails {
  node: LabNode;
  profile: Profile;
  state: Record<string, Json>;
  active_paths: string[];
}
export interface LabEvent {
  event_id: string;
  event_type: string;
  simulation_id: string;
  sequence: number;
  simulation_time_ms: number;
  step_id: string | null;
  source_id: string | null;
  target_id: string | null;
  conversation_id: string | null;
  message_id: string | null;
  payload: Record<string, Json>;
}
export interface Lineage {
  simulation_time_ms: number;
  message_id: string;
  operation: string;
  location: string;
  artefact: string;
  container: string | null;
  detail: string;
}
export interface Topology {
  nodes: LabNode[];
  paths: Path[];
}
interface Clock {
  first_message_hop_sequence: number | null;
  simulation_id: string;
  epoch: number;
  sequence: number;
  status: Status;
  simulation_time_ms: number;
  next_step_ms: number | null;
  step_delay_ms: number;
  initialised: boolean;
}
export interface Snapshot extends Clock {
  config: Config;
  random_seed: number;
  topology: Topology;
  profiles: Profile[];
  observer: { id: string; lifecycle: string };
  messages: Message[];
  devices: Device[];
  lineage: Lineage[];
  outcomes: Record<string, Outcome>;
}
export interface Delta extends Clock {
  nodes: LabNode[];
  paths: Path[];
  messages: Message[];
  devices: Device[];
  lineage: Lineage[];
  outcomes: Record<string, Outcome>;
  events: LabEvent[];
}
export type CommandType =
  | 'run'
  | 'pause'
  | 'resume'
  | 'step'
  | 'step_to_first_message_hop'
  | 'stop'
  | 'reset'
  | 'set_playback_delay'
  | 'request_state'
  | 'request_topology'
  | 'request_node_details'
  | 'request_protocol_state'
  | 'set_node_availability'
  | 'set_polling_enabled'
  | 'block_network_path'
  | 'restore_network_path'
  | 'block_stage_boundary'
  | 'restore_stage_boundary'
  | 'set_staged_messages'
  | 'request_device_logs'
  | 'request_artefact_lineage'
  | 'ping';
export interface CommandArgs {
  target?: string;
  enabled?: boolean;
  drop_in_flight?: boolean;
  delay_ms?: number;
  messages?: Record<string, string>;
}
export type Connection =
  | 'disconnected'
  | 'testing'
  | 'tested'
  | 'connecting'
  | 'connected'
  | 'reconnecting'
  | 'error';
export interface ClientState {
  firstDeparturePlayback: boolean;
  connection: Connection;
  http: string;
  ws: string;
  version: string;
  error: string;
  config: Config | null;
  snapshot: Snapshot | null;
  events: LabEvent[];
  pending: number;
  feedback: string;
}
