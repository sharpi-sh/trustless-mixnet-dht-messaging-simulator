import { render } from 'svelte/server';
import ConversationColumn from './ConversationColumn.svelte';
import { snapshot } from './fixtures/control-state';
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

test('shows the selected participant’s message history, address and last activity in the chat', () => {
  const first = snapshot.devices[0];
  const second = {
    ...first,
    id: 'receiver-2',
    label: 'Lena',
    logs: [
      {
        state: 'sent' as const,
        message_id: 'm',
        direction: 'reply' as const,
        conversation_id: 'c',
        text: 'From Lena',
        simulation_time_ms: 23,
      },
    ],
  };
  const { body } = render(ConversationColumn, {
    props: {
      role: second.role,
      selectedId: second.id,
      devices: [first, second],
      messages: [],
      address: '10.77.0.5',
    },
  });
  expect(body).toContain('data-chat-owner="receiver-2"');
  expect(body).toContain('10.77.0.5');
  expect(body).toContain('data-last-sent="23"');
  expect(body).toContain('From Lena');
});
