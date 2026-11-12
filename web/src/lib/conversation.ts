import type { DeviceLog } from './types';

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

export function chatRows(logs: DeviceLog[]) {
  return logs.filter(
    (row) =>
      row.state === 'sent' ||
      row.state === 'replied' ||
      row.state === 'received',
  );
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
