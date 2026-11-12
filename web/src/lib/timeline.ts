import type { LabEvent, LabNode } from './types';

export const categories = [
  'All events',
  'Participants',
  'Tor',
  'Mixnet',
  'DHT',
  'Storage',
  'Routing',
  'Availability',
  'Polling',
  'Encryption/decryption',
  'Failures/retries',
] as const;
export type Category = (typeof categories)[number];
export type Filters = {
  category: Category;
  node: string;
  message: string;
  query: string;
};

function categoryMatch(
  category: Category,
  e: LabEvent,
  nodes: Map<string, LabNode['kind']>,
) {
  const name = e.event_type;
  const touches = (kind: LabNode['kind']) =>
    nodes.get(e.source_id ?? '') === kind ||
    nodes.get(e.target_id ?? '') === kind;
  switch (category) {
    case 'All events':
      return true;
    case 'Participants':
      return touches('person') || name.startsWith('device_');
    case 'Tor':
      return touches('tor') || name.startsWith('tor_');
    case 'Mixnet':
      return /^(mix|sphinx|cover_|packet_)/.test(name);
    case 'DHT':
      return name.startsWith('kademlia_') || touches('dht');
    case 'Storage':
      return (
        /^(fragment_|manifest_|message_chunked|message_reconstructed)/.test(
          name,
        ) || touches('storage')
      );
    case 'Routing':
      return /route|transit|forward|packet_retry|boundary|network_path/.test(
        name,
      );
    case 'Availability':
      return /status_changed|outage|path_blocked|path_restored|boundary_blocked|boundary_restored/.test(
        name,
      );
    case 'Polling':
      return name.includes('poll');
    case 'Encryption/decryption':
      return /encrypt|decrypt|key_|manifest_|reconstructed/.test(name);
    case 'Failures/retries':
      return (
        /fail|timeout|retry|rejected|error|dropped/.test(name) ||
        e.payload.success === false
      );
  }
}

export function makeTimelineIndex() {
  let previous = '',
    scanned = 0,
    first: LabEvent | undefined;
  let matches: LabEvent[] = [];
  return (
    events: LabEvent[],
    filter: Filters,
    nodes: Map<string, LabNode['kind']>,
  ) => {
    const key = JSON.stringify(filter);
    if (key !== previous || first !== events[0] || scanned > events.length) {
      matches = [];
      scanned = 0;
      previous = key;
      first = events[0];
    }
    const search = filter.query.trim().toLowerCase();
    for (; scanned < events.length; scanned++) {
      const e = events[scanned];
      if (!categoryMatch(filter.category, e, nodes)) continue;
      if (
        filter.node &&
        e.source_id !== filter.node &&
        e.target_id !== filter.node &&
        e.payload.person_id !== filter.node &&
        e.payload.peer !== filter.node
      )
        continue;
      if (filter.message && e.message_id !== filter.message) continue;
      if (
        search &&
        ![
          e.event_type,
          e.conversation_id,
          e.source_id,
          e.target_id,
          e.payload.packet_id,
          e.payload.token,
        ].some((v) => typeof v === 'string' && v.toLowerCase().includes(search))
      )
        continue;
      matches.push(e);
    }
    return { rows: matches, count: matches.length };
  };
}

export function eventSummary(e: LabEvent) {
  const p = e.payload;
  if (typeof p.reason === 'string') return p.reason;
  if (Array.isArray(p.ordered_route)) return p.ordered_route.join(' → ');
  if (typeof p.method === 'string')
    return p.method + (p.peer ? ' · ' + p.peer : '');
  if (typeof p.delay_ms === 'number')
    return p.delay_ms + ' ms' + (p.packet_id ? ' · ' + p.packet_id : '');
  if (typeof p.observation === 'string') return p.observation;
  if (typeof p.online === 'boolean') return p.online ? 'Online' : 'Offline';
  if (typeof p.state === 'string') return p.state;
  if (typeof p.step === 'object' && p.step && !Array.isArray(p.step))
    return String(p.step.step_type ?? '');
  return (
    [p.integrity, p.packet_id, p.path_id, p.token].find(
      (v) => typeof v === 'string' && v,
    ) || ''
  );
}
