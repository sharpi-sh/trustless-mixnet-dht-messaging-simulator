import type { DeviceLog, Message } from './types';

export function logicalStamp(ms: number) {
  const whole = Math.floor(ms / 1000);
  const hours = Math.floor(whole / 3600);
  const minutes = Math.floor(whole / 60) % 60;
  return (
    (hours ? hours + ':' : '') +
    String(minutes).padStart(2, '0') +
    ':' +
    String(whole % 60).padStart(2, '0') +
    '.' +
    String(ms % 1000).padStart(3, '0')
  );
}

export function verifiedSigner(row: DeviceLog): string | null {
  return row.state === 'received' &&
    row.verified_signer_id &&
    row.signing_fingerprint
    ? row.verified_signer_id
    : null;
}

export function chatRows(logs: DeviceLog[]) {
  return logs.filter(
    (row) =>
      row.state === 'sent' ||
      row.state === 'replied' ||
      row.state === 'received',
  );
}

export function inboxContacts(
  logs: DeviceLog[],
  messages: Message[],
  owner?: string,
) {
  const peers = new Map<string, string>();
  for (const message of messages) {
    if (message.target_id === owner)
      peers.set(message.conversation_id, message.sender_id);
    else if (message.sender_id === owner)
      peers.set(message.conversation_id, message.target_id);
  }

  const received = new Map<string, number>();
  for (const row of logs) {
    const peer = peers.get(row.conversation_id);
    if (row.state === 'received' && peer)
      received.set(peer, (received.get(peer) ?? 0) + 1);
  }
  return { peers, received };
}

export function inboxPreviewRows(
  logs: DeviceLog[],
  peers: ReadonlyMap<string, string>,
) {
  const latest = new Map<
    string,
    { peer: string; row: DeviceLog; index: number }
  >();
  logs.forEach((row, index) => {
    const peer = peers.get(row.conversation_id);
    if (row.state === 'received' && peer)
      latest.set(peer, { peer, row, index });
  });
  return [...latest.values()].sort((a, b) => a.index - b.index);
}

export function lastActivity(logs: DeviceLog[]) {
  let sent: number | null = null,
    received: number | null = null;
  for (const row of logs) {
    if (row.state === 'sent' || row.state === 'replied')
      sent = row.simulation_time_ms;
    if (row.state === 'received') received = row.simulation_time_ms;
  }
  return { sent, received };
}
