import type { Json, LabEvent, Path } from './types';

export type Fields = Record<string, Json>;
export function fields(value: Json | undefined): Fields {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value
    : {};
}
export function rows(value: Json | undefined): Fields[] {
  return Array.isArray(value) ? value.map(fields) : [];
}
export function display(value: Json | undefined): string {
  if (value === undefined || value === null) return '—';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (Array.isArray(value)) return value.map(display).join(', ');
  if (typeof value === 'object')
    return Object.entries(value)
      .map(([key, item]) => key + ' ' + display(item))
      .join(' · ');
  return String(value);
}
export function time(value: Json | undefined) {
  return typeof value === 'number'
    ? value.toLocaleString('en-GB') + ' ms'
    : '—';
}
export function peerPath(
  paths: Pick<Path, 'id' | 'source_id' | 'target_id'>[],
  owner: string,
  peer: string,
) {
  return paths.find(
    (p) =>
      (p.source_id === owner && p.target_id === peer) ||
      (p.target_id === owner && p.source_id === peer),
  )?.id;
}
export function relevant(
  events: LabEvent[],
  nodeId: string,
  path: Pick<Path, 'id' | 'source_id' | 'target_id'> | undefined,
): LabEvent[] {
  return events
    .filter((e) =>
      nodeId
        ? e.source_id === nodeId ||
          e.target_id === nodeId ||
          e.payload.person_id === nodeId ||
          e.payload.peer === nodeId
        : path &&
          (e.payload.path_id === path.id ||
            (e.source_id === path.source_id &&
              e.target_id === path.target_id) ||
            (e.source_id === path.target_id && e.target_id === path.source_id)),
    )
    .reverse();
}
