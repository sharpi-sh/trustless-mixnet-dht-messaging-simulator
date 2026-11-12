import type { Channel, IPHop, Json } from './types';

export const channelNames: Record<Channel, string> = {
  tor: 'Tor',
  shadowsocks: 'Outline Shadowsocks',
  direct: 'Direct connection',
};

export function isChannel(kind: string): kind is Channel {
  return kind === 'tor' || kind === 'shadowsocks' || kind === 'direct';
}

export function recordedIPHop(value: Json | undefined): IPHop | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const {
    source_ip,
    destination_ip,
    observed_source_ip,
    observer,
    description,
    local,
  } = value;
  if (
    typeof source_ip !== 'string' ||
    typeof destination_ip !== 'string' ||
    typeof observed_source_ip !== 'string' ||
    typeof observer !== 'string' ||
    typeof description !== 'string' ||
    typeof local !== 'boolean'
  )
    return null;
  return {
    source_ip,
    destination_ip,
    observed_source_ip,
    observer,
    description,
    local,
  };
}
