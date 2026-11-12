import { render } from 'svelte/server';
import { expect, test } from 'vitest';
import { recordedIPHop } from './channels';
import IPObservation from './IPObservation.svelte';
import type { IPHop } from './types';

const hop: IPHop = {
  source_ip: '10.77.0.1',
  destination_ip: '10.77.0.2',
  observed_source_ip: '10.77.0.1',
  observer: 'shadowsocks-sender-1',
  description: 'The proxy sees the device address.',
  local: false,
};

test.each([
  ['in_transit', 'In transit'],
  ['not_received', 'Peer did not receive this transit'],
  ['configured', 'Configured projection'],
])('distinguishes %s from a received IP observation', (observation, label) => {
  const { body } = render(IPObservation, {
    props: { hop, heading: 'Trace', observation },
  });
  expect(body).toContain(label);
  expect(body).toContain('Projected source IP');
  expect(body).not.toContain('Observed source IP');
});

test('handles missing, malformed and complete recorded IP fields', () => {
  expect(recordedIPHop(undefined)).toBeNull();
  expect(recordedIPHop({ source_ip: 'unknown' })).toBeNull();
  expect(recordedIPHop({ ...hop })).toEqual(hop);
});
