import { render } from 'svelte/server';
import { expect, test } from 'vitest';
import ConversationColumn from './ConversationColumn.svelte';
import SignatureReceipt from './SignatureReceipt.svelte';
import { snapshot } from './fixtures/control-state';
import type { DeviceLog } from './types';

const received: DeviceLog = {
  message_id: 'msg-1',
  conversation_id: 'conv-1',
  state: 'received',
  direction: 'forward',
  text: 'Signed message',
  simulation_time_ms: 13,
};

test('the chat names the verified signer and exposes the complete signing fingerprint', () => {
  const signer = snapshot.devices[1];
  const receipt = {
    ...received,
    verified_signer_id: signer.id,
    signing_fingerprint: signer.signing_fingerprint,
  };
  const body = render(ConversationColumn, {
    props: {
      role: 'receiver',
      devices: [{ ...snapshot.devices[0], logs: [receipt] }, signer],
      messages: snapshot.messages,
    },
  }).body;
  expect(body).toContain('Signature verified');
  expect(body).toContain(signer.id);
  expect(body).toContain(signer.label);
  expect(body).toContain(signer.signing_fingerprint);
});

test.each([
  {},
  { verified_signer_id: 'sender-1' },
  { signing_fingerprint: 'a'.repeat(64) },
])(
  'receipts without complete verification evidence stay unverified',
  (partial) => {
    const body = render(ConversationColumn, {
      props: {
        role: 'receiver',
        devices: [
          { ...snapshot.devices[0], logs: [{ ...received, ...partial }] },
        ],
        messages: snapshot.messages,
      },
    }).body;
    expect(body).toContain('Unverified sender');
    expect(body).toContain('No signature evidence recorded');
    expect(body).not.toContain('Signature verified');
  },
);

test('outgoing entries do not report receiver verification', () => {
  const row: DeviceLog = {
    ...received,
    state: 'sent',
    verified_signer_id: 'sender-1',
    signing_fingerprint: 'a'.repeat(64),
  };
  expect(render(SignatureReceipt, { props: { row } }).body).not.toContain(
    'Signature verified',
  );
});
