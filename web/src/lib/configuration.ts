import type { Config } from './types';

type NumericKey = Exclude<
  { [K in keyof Config]: Config[K] extends number ? K : never }[keyof Config],
  undefined
>;
export type NumericField = [
  NumericKey,
  string,
  number,
  number,
  ('integer' | 'positive' | 'decimal')?,
];

export const fieldHelp: Record<string, string> = {
  participant_channel:
    'How this person reaches their first network provider: through Tor, an Outline proxy, or directly.',
  min_nodes: 'The number of mix servers used across the three routing layers.',
  max_nodes: 'The largest mix-server count Python may choose for this run.',
  randomise_count:
    'Let Python choose the mix-server count between the minimum and maximum.',
  pairing_strategy:
    'Chooses which senders exchange messages with which recipients.',
  pair_count:
    'How many different sender and recipient pairs Python creates at random.',
  exchanges: 'How many message-and-reply rounds each conversation contains.',
  random_seed:
    'A number that makes the same setup produce the same simulated decisions again.',
  step_delay_ms:
    'Real waiting time between displayed steps. Zero plays without an added visual pause.',
  pattern:
    'Controls whether nodes stay online or become unavailable during the run.',
  outage_node: 'The exact node ID that will be taken offline, such as mix-1.',
  outage_start: 'The simulated time when this outage begins.',
  outage_duration:
    'How long the selected node remains offline in simulated time.',
  polling_enabled:
    'Makes recipients check their provider for new message handles on a timer.',
  polling_override:
    'Lets this recipient use or ignore the main polling setting.',
  polling_interval_ms:
    'How often each enabled recipient checks for new messages. The default is 2 seconds.',
  poll_batch:
    'The fixed number of padded slots returned by each provider poll.',
  dht_nodes:
    'The number of servers participating in distributed message lookup.',
  storage_nodes:
    'The number of vault servers available to hold encrypted message pieces.',
  replicas: 'How many vaults receive a copy of each encrypted message piece.',
  chunk_bytes:
    'The target size of each encrypted message piece before replication.',
  operator_count:
    'The number of simulated organisations responsible for network nodes.',
  base_transit_delay_ms:
    'The normal simulated travel time across each network connection.',
  jitter_min_ms:
    'The smallest extra random travel delay added to a connection.',
  jitter_max_ms: 'The largest extra random travel delay added to a connection.',
  ack_timeout_ms:
    'How long Python waits before treating a network hand-off as failed.',
  max_retries:
    'How many fresh end-to-end attempts a failed message may receive.',
  mu_per_second:
    'Controls mix holding time. A larger value produces shorter average holds.',
  payload_rate_per_minute:
    'How often a sender gets an opportunity to send a real queued message.',
  client_loop_rate_per_minute:
    'How often a device sends a test packet that loops back to itself.',
  drop_cover_rate_per_minute:
    'How often cover packets are created to end inside the mix network.',
  mix_loop_rate_per_minute:
    'How often a mix server sends cover traffic around the network and back.',
  failure_probability:
    'Chance that a normally changing node starts an outage when checked.',
  initial_offline_probability:
    'Chance that a node begins the simulation offline.',
  always_online_probability:
    'Chance that a node is kept online for the whole simulation.',
  always_offline_probability:
    'Chance that a node is kept offline for the whole simulation.',
  min_online_ms:
    'Minimum simulated time a changing node remains online between outages.',
  min_outage_ms: 'Shortest randomly generated outage in simulated time.',
  max_outage_ms: 'Longest randomly generated outage in simulated time.',
};

export const networkFields: NumericField[] = [
  ['sender_count', 'Senders', 1, 10],
  ['receiver_count', 'Receivers', 1, 10],
  ['min_nodes', 'Minimum mix nodes', 6, 20],
  ['max_nodes', 'Maximum mix nodes', 6, 20],
  ['exchanges', 'Exchanges per conversation', 1, 10],
  ['pair_count', 'Random pair count', 1, 100],
  ['step_delay_ms', 'Playback delay (ms)', 0, 2000],
];
export const pollingFields: NumericField[] = [
  ['polling_interval_ms', 'Polling interval (ms)', 100, 600000],
  ['poll_batch', 'Cells per response', 1, 16],
];
export const storageFields: NumericField[] = [
  ['dht_nodes', 'DHT nodes', 2, 64],
  ['storage_nodes', 'Storage nodes', 1, 32],
  ['replicas', 'Replicas per chunk', 1, 8],
  ['chunk_bytes', 'Chunk size (bytes)', 32, 4096],
  ['operator_count', 'Operators', 1, 100],
];
export const transportFields: NumericField[] = [
  ['base_transit_delay_ms', 'Path transit delay (ms)', 0, 60000],
  ['jitter_min_ms', 'Minimum jitter (ms)', 0, 60000],
  ['jitter_max_ms', 'Maximum jitter (ms)', 0, 60000],
  ['ack_timeout_ms', 'Acknowledgement timeout (ms)', 1, 60000],
  ['max_retries', 'Maximum retries', 0, 10],
];
export const loopixFields: NumericField[] = [
  ['mu_per_second', 'Mix delay rate (per second)', 0, 100, 'positive'],
  ['payload_rate_per_minute', 'Payloads per minute', 0, 600, 'positive'],
  [
    'client_loop_rate_per_minute',
    'Client loops per minute',
    0,
    600,
    'positive',
  ],
  ['drop_cover_rate_per_minute', 'Drop packets per minute', 0, 600, 'positive'],
  ['mix_loop_rate_per_minute', 'Mix loops per minute', 0, 600, 'positive'],
];
export const outageFields: NumericField[] = [
  ['failure_probability', 'Failure probability', 0, 1, 'decimal'],
  [
    'initial_offline_probability',
    'Initially offline probability',
    0,
    1,
    'decimal',
  ],
  ['always_online_probability', 'Always online probability', 0, 1, 'decimal'],
  ['always_offline_probability', 'Always offline probability', 0, 1, 'decimal'],
  ['min_online_ms', 'Minimum online time (ms)', 1, 3600000],
  ['min_outage_ms', 'Minimum outage (ms)', 0, 3600000],
  ['max_outage_ms', 'Maximum outage (ms)', 0, 3600000],
];

type Pairing = Pick<
  Config,
  | 'pairing_strategy'
  | 'sender_count'
  | 'receiver_count'
  | 'pair_count'
  | 'exchanges'
>;

export function conversationCount(cfg: Pairing) {
  if (cfg.pairing_strategy === 'random_pairs') return cfg.pair_count;
  if (cfg.pairing_strategy === 'one_to_all') return cfg.receiver_count;
  return cfg.sender_count;
}

export function configurationError(cfg: Config): string {
  for (const [key, name, min, max, rule = 'integer'] of [
    ...networkFields,
    ...pollingFields,
    ...storageFields,
    ...transportFields,
    ...loopixFields,
    ...outageFields,
  ]) {
    const value = cfg[key];
    if (
      !Number.isFinite(value) ||
      value < min ||
      value > max ||
      (rule === 'integer' && !Number.isInteger(value)) ||
      (rule === 'positive' && value <= 0)
    ) {
      return rule === 'positive'
        ? `${name} must be greater than zero and at most ${max}.`
        : `${name} must be ${rule === 'integer' ? 'a whole number ' : ''}between ${min} and ${max}.`;
    }
  }
  if (
    cfg.random_seed != null &&
    (!Number.isSafeInteger(cfg.random_seed) || cfg.random_seed < 0)
  )
    return 'Use a non-negative, safe integer for the random seed.';
  if (cfg.min_nodes > cfg.max_nodes)
    return 'Maximum mix nodes must equal or exceed minimum mix nodes.';
  if (cfg.jitter_min_ms > cfg.jitter_max_ms)
    return 'Maximum jitter must equal or exceed minimum jitter.';
  if (cfg.min_outage_ms > cfg.max_outage_ms)
    return 'Maximum outage must equal or exceed minimum outage.';
  if (cfg.replicas > cfg.storage_nodes)
    return 'Replica count cannot exceed the number of storage nodes.';
  if (cfg.always_offline_probability + cfg.always_online_probability > 1)
    return 'Always online and always offline probabilities must add up to at most one.';
  if (
    cfg.pairing_strategy === 'one_to_one_pairs' &&
    cfg.sender_count !== cfg.receiver_count
  )
    return 'One-to-one pairs require equal sender and receiver counts.';
  if (
    cfg.pairing_strategy === 'random_pairs' &&
    cfg.pair_count > cfg.sender_count * cfg.receiver_count
  )
    return 'Random pair count exceeds the number of distinct pairs.';
  if (
    cfg.scheduled_outages.some(
      (row) =>
        !row.node_id.trim() ||
        !Number.isSafeInteger(row.start_ms) ||
        row.start_ms < 0 ||
        !Number.isSafeInteger(row.duration_ms) ||
        row.duration_ms < 0,
    )
  )
    return 'Each scheduled outage needs a node ID and non-negative integer times.';
  return '';
}

export function participantIds(role: 'sender' | 'receiver', count: number) {
  return Array.from(
    { length: Math.min(10, Math.max(0, count || 0)) },
    (_, i) => `${role}-${i + 1}`,
  );
}

export function prepareConfig(cfg: Config): Config {
  const known = participantIds('receiver', cfg.receiver_count);
  const active = new Set([
    ...known,
    ...participantIds('sender', cfg.sender_count),
  ]);
  return {
    ...cfg,
    ...(cfg.participant_channels && {
      participant_channels: Object.fromEntries(
        Object.entries(cfg.participant_channels).filter(([id]) =>
          active.has(id),
        ),
      ),
    }),
    random_seed: cfg.random_seed ?? null,
    max_nodes: cfg.randomise_count ? cfg.max_nodes : cfg.min_nodes,
    polling_overrides: Object.fromEntries(
      Object.entries(cfg.polling_overrides).filter(([id]) =>
        known.includes(id),
      ),
    ),
    scheduled_outages:
      cfg.pattern === 'scheduled'
        ? cfg.scheduled_outages.map((s) => ({
            ...s,
            node_id: s.node_id.trim(),
          }))
        : [],
  };
}
