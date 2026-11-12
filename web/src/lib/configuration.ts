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

export const networkFields: NumericField[] = [
  ['sender_count', 'Senders', 1, 10],
  ['receiver_count', 'Receivers', 1, 10],
  ['min_nodes', 'Minimum mix nodes', 10, 20],
  ['max_nodes', 'Maximum mix nodes', 10, 20],
  ['exchanges', 'Exchanges per conversation', 1, 10],
  ['pair_count', 'Random pair count', 1, 100],
  ['step_delay_ms', 'Playback delay (ms)', 1, 2000],
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

export function prepareConfig(cfg: Config): Config {
  const known = Array.from(
    { length: cfg.receiver_count },
    (_, i) => `receiver-${i + 1}`,
  );
  return {
    ...cfg,
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
