import { expect, test } from 'vitest';
import { fields, rows, display, peerPath, relevant, time } from './inspector';
import type { LabEvent } from './types';

const path = {
  id: 'path-from-backend',
  source_id: 'mix-A',
  target_id: 'mix-B',
};
function event(sequence: number): LabEvent {
  return {
    event_id: 'e-' + sequence,
    event_type: 'step',
    simulation_id: 'sim',
    sequence,
    simulation_time_ms: 0,
    step_id: null,
    source_id: 'mix-B',
    target_id: 'mix-A',
    conversation_id: null,
    message_id: null,
    payload: {},
  };
}

test('peer highlights refer only to configured paths in either orientation', () => {
  expect(peerPath([path], 'mix-B', 'mix-A')).toBe(path.id);
  expect(peerPath([], 'mix-B', 'mix-A')).toBeUndefined();
});

test('node and path histories keep newest records first without mutating the event stream', () => {
  const events = [
    event(1),
    {
      ...event(2),
      source_id: null,
      target_id: null,
      payload: { path_id: path.id },
    },
    {
      ...event(3),
      source_id: 'elsewhere',
      target_id: null,
      payload: { person_id: 'sender-1' },
    },
  ];
  expect(relevant(events, 'mix-A', undefined).map((e) => e.sequence)).toEqual([
    1,
  ]);
  expect(relevant(events, '', path).map((e) => e.sequence)).toEqual([2, 1]);
  expect(
    relevant(events, 'sender-1', undefined).map((e) => e.sequence),
  ).toEqual([3]);
  expect(relevant(events, '', path, 1).map((e) => e.sequence)).toEqual([2]);
  expect(events.map((e) => e.sequence)).toEqual([1, 2, 3]);
});

test('state entries keep fixed-width identifiers and distinguish zero time from unknown', () => {
  const hex = '0'.repeat(39) + '7';
  expect(rows([{ id: hex }])[0].id).toBe(hex);
  expect(fields(null)).toEqual({});
  expect(display(false)).toBe('No');
  expect(time(0)).toBe('0 ms');
  expect(time(null)).toBe('—');
});
