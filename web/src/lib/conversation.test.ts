import { expect, test } from 'vitest';
import { chatRows, lastActivity, logicalStamp } from './conversation';
import type { DeviceLog } from './types';

test('preserves each device log’s original order, including equal timestamps', () => {
  const entry = (
    state: DeviceLog['state'],
    message_id: string,
    simulation_time_ms: number,
  ): DeviceLog => ({
    state,
    message_id,
    simulation_time_ms,
    text: message_id,
    direction: 'forward',
    conversation_id: 'c',
  });
  const logs = [
    entry('staged', 'x', 0),
    entry('sent', 'a', 0),
    entry('delivered', 'b', 1200),
    entry('received', 'b', 1200),
    entry('replied', 'c', 1200),
  ];
  expect(chatRows(logs).map((r) => r.message_id)).toEqual(['a', 'b', 'c']);
  expect(lastActivity(logs)).toEqual({ sent: 1200, received: 1200 });
  expect(lastActivity(logs.slice(0, 2))).toEqual({ sent: 0, received: null });
  expect(logicalStamp(1200)).toBe('00:01.200');
  expect(logicalStamp(3600500)).toBe('1:00:00.500');
});
