import { render } from 'svelte/server';
import ConversationColumn from './ConversationColumn.svelte';
import { snapshot } from './fixtures/control-state';
import { expect, test } from 'vitest';
import {
  chatRows,
  inboxPreviewRows,
  lastActivity,
  logicalStamp,
} from './conversation';
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

test('keeps only the latest received message per sender in inbox order', () => {
  const row = (
    state: DeviceLog['state'],
    message_id: string,
    conversation_id: string,
  ): DeviceLog => ({
    state,
    message_id,
    conversation_id,
    simulation_time_ms: 1,
    text: message_id,
    direction: 'forward',
  });
  const peers = new Map([
    ['alice-chat', 'sender-1'],
    ['nina-chat', 'sender-2'],
  ]);
  const previews = inboxPreviewRows(
    [
      row('received', 'alice-old', 'alice-chat'),
      row('replied', 'bob-reply', 'alice-chat'),
      row('received', 'nina-latest', 'nina-chat'),
      row('received', 'alice-latest', 'alice-chat'),
      row('received', 'unknown', 'unknown-chat'),
    ],
    peers,
  );
  expect(previews.map(({ peer, row }) => [peer, row.message_id])).toEqual([
    ['sender-2', 'nina-latest'],
    ['sender-1', 'alice-latest'],
  ]);
});

test('shows participant activity while hiding receiver replies in inbox mode', () => {
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
  expect(body).toContain('No messages yet.');
  expect(body).not.toContain('From Lena');
});

test('renders one portrait per incoming contact and counts only received entries', () => {
  const first = snapshot.messages[0];
  const bob = snapshot.devices[0];
  const alice = {
    ...bob,
    id: first.sender_id,
    label: 'Alice',
    role: 'sender' as const,
  };
  const nina = { ...alice, id: 'sender-2', label: 'Nina' };
  const chris = { ...alice, id: 'sender-3', label: 'Chris' };
  const messages = [
    first,
    ...[alice, nina, chris].map((peer, i) => ({
      ...first,
      id: 'm' + i,
      conversation_id: 'c' + i,
      sender_id: peer.id,
    })),
  ];
  const logs = messages.map((m, i) => ({
    ...bob.logs[0],
    message_id: m.id,
    conversation_id: m.conversation_id,
    state: i < 3 ? ('received' as const) : ('staged' as const),
  }));
  const { body } = render(ConversationColumn, {
    props: {
      role: 'receiver',
      devices: [
        {
          ...bob,
          logs: [
            ...logs,
            { ...logs[2], state: 'delivered' },
            {
              ...logs[0],
              state: 'replied',
              message_id: 'receiver-reply',
              text: 'Receiver reply hidden from inbox',
            },
          ],
        },
        alice,
        nina,
        chris,
      ],
      messages,
    },
  });
  expect(body).toContain('aria-label="Alice, 2 messages received"');
  expect(body).toContain('aria-label="Nina, 1 message received"');
  expect(body).toContain('aria-label="Open conversation with Alice"');
  expect(body).toContain('aria-label="Open conversation with Nina"');
  expect(body).toContain('src="/avatars/sender-1.jpg"');
  expect(body).not.toContain('/avatars/sender-3.jpg');
  expect(body).not.toContain('Receiver reply hidden from inbox');
  expect(body).not.toContain('<select');
});
