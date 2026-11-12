import { expect, test } from 'vitest';
import {
  conversationCount,
  prepareConfig,
  configurationError,
  networkFields,
  storageFields,
  pollingFields,
  loopixFields,
  transportFields,
  outageFields,
} from './configuration';
import type { Config } from './types';

function valid(): Config {
  // Run each numeric validator against its official lower or first positive bound.
  const settings = Object.fromEntries(
    [
      ...networkFields,
      ...storageFields,
      ...pollingFields,
      ...loopixFields,
      ...transportFields,
      ...outageFields,
    ].map(([key, , minimum, , rule]) => [
      key,
      rule === 'positive' ? 0.1 : minimum,
    ]),
  );
  return {
    ...settings,
    pairing_strategy: 'all_to_one',
    randomise_count: false,
    random_seed: null,
    pattern: 'always_online',
    polling_overrides: {},
    polling_enabled: true,
    scheduled_outages: [],
  } as Config;
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
