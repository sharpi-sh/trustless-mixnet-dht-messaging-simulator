import { expect, test } from 'vitest';
import {
  conversationCount,
  prepareConfig,
  configurationError,
} from './configuration';
import type { Config } from './types';

function valid(): Config {
  return {
    sender_count: 1,
    receiver_count: 1,
    min_nodes: 10,
    max_nodes: 10,
    randomise_count: false,
    pairing_strategy: 'all_to_one',
    pair_count: 1,
    exchanges: 1,
    random_seed: null,
    polling_enabled: true,
    polling_overrides: {},
    polling_interval_ms: 100,
    poll_batch: 1,
    base_transit_delay_ms: 1,
    jitter_min_ms: 0,
    jitter_max_ms: 1,
    mu_per_second: 0.1,
    payload_rate_per_minute: 1,
    client_loop_rate_per_minute: 1,
    drop_cover_rate_per_minute: 1,
    mix_loop_rate_per_minute: 1,
    dht_nodes: 2,
    storage_nodes: 1,
    replicas: 1,
    chunk_bytes: 32,
    pattern: 'always_online',
    failure_probability: 0,
    min_outage_ms: 0,
    max_outage_ms: 1,
    min_online_ms: 1,
    initial_offline_probability: 0,
    always_offline_probability: 0,
    always_online_probability: 0,
    scheduled_outages: [],
    operator_count: 1,
    max_retries: 0,
    ack_timeout_ms: 1,
    step_delay_ms: 1,
  };
}

test('pairing choices count exchanges in both directions', () => {
  const cfg = {
    ...valid(),
    sender_count: 3,
    receiver_count: 4,
    pair_count: 5,
    exchanges: 2,
  };
  for (const [strategy, conversations] of [
    ['all_to_one', 3],
    ['one_to_all', 4],
    ['random_pairs', 5],
  ] as const) {
    expect(
      conversationCount({ ...cfg, pairing_strategy: strategy }) *
        cfg.exchanges *
        2,
    ).toBe(conversations * 4);
  }
  expect(
    configurationError({ ...cfg, pairing_strategy: 'one_to_one_pairs' }),
  ).toMatch(/equal sender/);
  expect(
    configurationError({
      ...cfg,
      pairing_strategy: 'random_pairs',
      pair_count: 13,
    }),
  ).toMatch(/distinct pairs/);
});

test('fixed node count, visible outages and active receiver overrides reach Python', () => {
  const cfg = {
    ...valid(),
    min_nodes: 19,
    max_nodes: 15,
    polling_overrides: { 'receiver-1': false, 'receiver-2': true },
    scheduled_outages: [{ node_id: ' mix-1 ', start_ms: 10, duration_ms: 50 }],
  };
  const settings = prepareConfig(cfg);
  expect(settings.max_nodes).toBe(19);
  expect(settings.polling_overrides).toEqual({ 'receiver-1': false });
  expect(settings.scheduled_outages).toEqual([]);
  expect(
    prepareConfig({ ...cfg, pattern: 'scheduled' }).scheduled_outages[0]
      .node_id,
  ).toBe('mix-1');
  expect(configurationError(settings)).toBe('');
});

test('cross-field limits, probabilities and exact seed limits agree with the backend', () => {
  const cfg = valid();
  expect(
    configurationError({ ...cfg, jitter_min_ms: 2, jitter_max_ms: 1 }),
  ).toMatch(/Maximum jitter/);
  expect(configurationError({ ...cfg, mu_per_second: 0 })).toMatch(
    /greater than zero/,
  );
  expect(configurationError({ ...cfg, replicas: 2, storage_nodes: 1 })).toMatch(
    /Replica count/,
  );
  expect(configurationError({ ...cfg, random_seed: 2 ** 53 })).toMatch(
    /random seed/,
  );
  expect(
    configurationError({
      ...cfg,
      always_offline_probability: 0.6,
      always_online_probability: 0.5,
    }),
  ).toMatch(/at most one/);
  expect(
    configurationError({
      ...cfg,
      scheduled_outages: [{ node_id: '', start_ms: 0, duration_ms: 200 }],
    }),
  ).toMatch(/node ID/);
});

test('accepts zero wall-clock pacing while keeping the configured logical delays', () => {
  const cfg = { ...valid(), step_delay_ms: 0, base_transit_delay_ms: 400 };
  expect(configurationError(cfg)).toBe('');
  expect(prepareConfig(cfg).base_transit_delay_ms).toBe(400);
  expect(configurationError({ ...cfg, step_delay_ms: -1 })).toMatch(
    /Playback delay/,
  );
});

test('only submits channel selections for participants still configured', () => {
  const cfg: Config = {
    ...valid(),
    sender_count: 3,
    participant_channels: {
      'sender-2': 'shadowsocks',
      'sender-3': 'direct',
      'receiver-1': 'direct',
    },
  };
  expect(prepareConfig(cfg).participant_channels).toEqual(
    cfg.participant_channels,
  );
  expect(
    prepareConfig({ ...cfg, sender_count: 2 }).participant_channels,
  ).toEqual({ 'sender-2': 'shadowsocks', 'receiver-1': 'direct' });
  expect(prepareConfig(valid())).not.toHaveProperty('participant_channels');
});
