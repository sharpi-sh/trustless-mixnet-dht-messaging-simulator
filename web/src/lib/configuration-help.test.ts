import { render } from 'svelte/server';
import { expect, test } from 'vitest';
import Configuration from './Configuration.svelte';
import { fieldHelp } from './configuration';
import { snapshot } from './fixtures/control-state';

test('every setup field exposes a concise keyboard-accessible explanation', () => {
  const { body } = render(Configuration, {
    props: {
      defaults: {
        ...snapshot.config,
        pattern: 'scheduled',
        randomise_count: true,
        pairing_strategy: 'random_pairs',
        participant_channels: {},
        scheduled_outages: [
          { node_id: 'mix-1', start_ms: 100, duration_ms: 500 },
        ],
      },
      participantLabels: { 'sender-1': 'Alice', 'receiver-1': 'Bob' },
      create: async () => {},
      busy: false,
    },
  });
  for (const help of Object.values(fieldHelp)) expect(body).toContain(help);
  expect(body).toContain('Information about Alice channel');
  expect(body).toContain('Information about Polling interval (ms)');
  expect(body).toContain('aria-label="Minimum mix nodes"');
  expect(body).toContain('aria-label="Random seed"');
});
