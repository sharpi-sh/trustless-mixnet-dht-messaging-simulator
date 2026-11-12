import type { CommandArgs, CommandType, Path } from './types';

export function boundaryStates(paths: Pick<Path, 'boundary' | 'blocked'>[]) {
  const summary = new Map<string, { total: number; blocked: number }>();
  for (const path of paths) {
    const state = summary.get(path.boundary) ?? { total: 0, blocked: 0 };
    state.total += 1;
    state.blocked += Number(path.blocked);
    summary.set(path.boundary, state);
  }
  return summary;
}

export function routeCommand(
  scope: 'path' | 'boundary',
  block: boolean,
  target: string,
  drop: boolean,
): { type: CommandType; args: CommandArgs } {
  const type =
    scope === 'path'
      ? block
        ? 'block_network_path'
        : 'restore_network_path'
      : block
        ? 'block_stage_boundary'
        : 'restore_stage_boundary';
  return {
    type,
    args: block && drop ? { target, drop_in_flight: true } : { target },
  };
}
