import { expect, test } from 'vitest';
import { boundaryStates, routeCommand } from './intervention-controls';
test('stage summaries preserve independently blocked paths and authoritative names', () => {
  const paths = [
    { boundary: 'mix ↔ provider', blocked: true },
    { boundary: 'device ↔ tor', blocked: false },
    { boundary: 'mix ↔ provider', blocked: false },
  ];
  const counts = boundaryStates(paths);
  expect([...counts.keys()]).toEqual(['mix ↔ provider', 'device ↔ tor']);
  expect(counts.get('mix ↔ provider')).toEqual({ total: 2, blocked: 1 });
  expect(counts.get('device ↔ tor')).toEqual({ total: 1, blocked: 0 });
});
test('in-flight drops are sent only when the requested path or boundary is being blocked', () => {
  expect(routeCommand('path', true, 'p', true)).toEqual({
    type: 'block_network_path',
    args: { target: 'p', drop_in_flight: true },
  });
  expect(routeCommand('path', true, 'p', false)).toEqual({
    type: 'block_network_path',
    args: { target: 'p' },
  });
  expect(routeCommand('boundary', false, 'b', true)).toEqual({
    type: 'restore_stage_boundary',
    args: { target: 'b' },
  });
  expect(routeCommand('boundary', true, 'b', true).type).toBe(
    'block_stage_boundary',
  );
  expect(routeCommand('path', false, 'p', true).type).toBe(
    'restore_network_path',
  );
});
