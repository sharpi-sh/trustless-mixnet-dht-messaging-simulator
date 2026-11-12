import { expect, test } from 'vitest';
import { eventSummary, makeTimelineIndex, type Filters } from './timeline';
import type { LabEvent, LabNode } from './types';
const nodes = new Map<string, LabNode['kind']>([
  ['a', 'person'],
  ['tor-a', 'tor'],
]);
const row = (
  sequence: number,
  type: string,
  payload: LabEvent['payload'] = {},
): LabEvent => ({
  sequence,
  event_type: type,
  payload,
  event_id: 'e' + sequence,
  simulation_id: 's',
  simulation_time_ms: 200 * sequence,
  step_id: null,
  source_id: 'a',
  target_id: 'tor-a',
  message_id: 'm',
  conversation_id: 'c',
});
const filters: Filters = {
  category: 'All events',
  node: '',
  message: '',
  query: '',
};
test('filters live increments, preserves sequence order and resets on epoch or filter changes', () => {
  const index = makeTimelineIndex(),
    a = row(1, 'path_transit_failed', { reason: 'blocked' }),
    b = row(2, 'receiver_polling_enabled');
  expect(index([a], filters, nodes).count).toBe(1);
  expect(index([a, b], filters, nodes).rows.map((e) => e.sequence)).toEqual([
    1, 2,
  ]);
  expect(
    index([a, b], { ...filters, category: 'Failures/retries' }, nodes).rows,
  ).toEqual([a]);
  expect(
    index(
      [a, b],
      {
        ...filters,
        category: 'Polling',
        query: 'receiver',
        message: 'm',
        node: 'a',
      },
      nodes,
    ).rows,
  ).toEqual([b]);
  expect(
    index(
      [row(1, 'simulation_started')],
      { ...filters, query: 'missing' },
      nodes,
    ).count,
  ).toBe(0);
  expect(index([a], { ...filters, node: 'elsewhere' }, nodes).count).toBe(0);
});
test('uses actual packet routes, failure reasons and logical delay in summaries', () => {
  expect(
    eventSummary(
      row(1, 'mixnet_route_constructed', {
        ordered_route: ['west', 'mix-2', 'east'],
      }),
    ),
  ).toBe('west → mix-2 → east');
  expect(
    eventSummary(row(2, 'path_transit_failed', { reason: 'unresponsive' })),
  ).toBe('unresponsive');
  expect(eventSummary(row(3, 'path_transit_started', { delay_ms: 45 }))).toBe(
    '45 ms',
  );
});
