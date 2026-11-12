<script lang="ts">
  import { get } from 'svelte/store';
  import NodeIcon from './NodeIcon.svelte';
  import type { LabClient } from './api';
  import type { Snapshot, CommandType, CommandArgs } from './types';
  import { boundaryStates, routeCommand } from './intervention-controls';

  let {
    lab,
    selectedNode,
    selectedPath,
    client,
    connected,
  }: {
    lab: Snapshot;
    selectedNode: string;
    selectedPath: string;
    client: LabClient;
    connected: boolean;
  } = $props();
  let node = $derived(lab.topology.nodes.find((n) => n.id === selectedNode));
  let path = $derived(lab.topology.paths.find((p) => p.id === selectedPath));
  let receivers = $derived(lab.devices.filter((p) => p.role === 'receiver'));
  let polling = $derived(receivers.filter((p) => p.polling_enabled).length);
  let selectedReceiver = $derived(receivers.find((p) => p.id === selectedNode));
  let boundaries = $derived(boundaryStates(lab.topology.paths));
  let boundary = $state('');
  let chosen = $derived(boundaries.get(boundary));
  let drop = $state(false);
  let pending = $state(false);
  let receipt = $state<{
    status: string;
    message: string;
    epoch: number;
    simulation: string;
  } | null>(null);
  let disabled = $derived(
    !connected ||
      pending ||
      ['failed', 'completed', 'stopped'].includes(lab.status),
  );

  async function send(message: string, type: CommandType, args: CommandArgs) {
    if (disabled) return;
    const scope = { epoch: lab.epoch, simulation: lab.simulation_id };
    pending = true;
    receipt = { ...scope, status: 'Pending', message };
    try {
      await client.command(type, args);
      receipt = { ...scope, status: 'Applied', message };
    } catch (cause) {
      const rejected = get(client.store).feedback === 'Command rejected';
      receipt = {
        ...scope,
        status: rejected ? 'Rejected' : 'Unconfirmed',
        message:
          message +
          ' · ' +
          (cause instanceof Error ? cause.message : String(cause)),
      };
    } finally {
      pending = false;
    }
  }
  function changeRoute(
    scope: 'path' | 'boundary',
    block: boolean,
    target: string,
  ) {
    const cmd = routeCommand(scope, block, target, drop);
    return send((block ? 'Block ' : 'Restore ') + target, cmd.type, cmd.args);
  }
</script>

<section class="interventions" aria-label="Runtime interventions">
  <header>
    <h2>Runtime controls</h2>
    {#if !connected}<span>Disconnected</span>{/if}
  </header>
  <div class="controls">
    <section class="unit">
      <h3>Receiver polling</h3>
      <p>{polling} of {receivers.length} enabled</p>
      <div class="actions">
        <button
          disabled={disabled || polling === receivers.length}
          aria-label="Enable all receiver polling"
          onclick={() =>
            send('Enable polling for all receivers', 'set_polling_enabled', {
              enabled: true,
            })}>Enable all</button
        >
        <button
          disabled={disabled || polling === 0}
          aria-label="Disable all receiver polling"
          onclick={() =>
            send('Disable polling for all receivers', 'set_polling_enabled', {
              enabled: false,
            })}>Disable all</button
        >
      </div>
      {#if selectedReceiver}
        <p>
          {selectedReceiver.label} · {selectedReceiver.polling_enabled
            ? 'Polling enabled'
            : 'Polling disabled'}
        </p>
        <button
          {disabled}
          onclick={() => {
            if (selectedReceiver)
              void send(
                (selectedReceiver.polling_enabled ? 'Disable ' : 'Enable ') +
                  selectedReceiver.id +
                  ' polling',
                'set_polling_enabled',
                {
                  target: selectedReceiver.id,
                  enabled: !selectedReceiver.polling_enabled,
                },
              );
          }}
        >
          {selectedReceiver.polling_enabled
            ? 'Disable receiver polling'
            : 'Enable receiver polling'}
        </button>
      {/if}
    </section>
    <div class="unit availability" role="group" aria-label="Node availability">
      <h3>Node availability</h3>
      {#if node}
        <div class="node-summary">
          <NodeIcon {node} size={28} />
          <div>
            <strong>{node.label}</strong>
            <span>{node.online ? 'Online' : 'Offline'}</span>
          </div>
        </div>
        <button
          {disabled}
          class:offline={!node.online}
          onclick={() => {
            if (node)
              void send(
                'Set ' + node.id + (node.online ? ' offline' : ' online'),
                'set_node_availability',
                { target: node.id, enabled: !node.online },
              );
          }}>{node.online ? 'Take node offline' : 'Bring node online'}</button
        >
      {:else}
        <p>Select a node to change its availability.</p>
      {/if}
    </div>
    <section class="unit routes">
      <h3>Path controls</h3>
      {#if path}
        <p>
          {path.source_id} ↔ {path.target_id} ·
          <strong>{path.blocked ? 'Blocked' : 'Available'}</strong>
        </p>
        {#if path.local}<p>Local handoff on the device.</p>{:else}<button
            {disabled}
            onclick={() => {
              if (path) void changeRoute('path', !path.blocked, path.id);
            }}>{path.blocked ? 'Restore path' : 'Block path'}</button
          >
        {/if}
      {:else}<p>Select a path on the map or in the inspector.</p>{/if}
      <label class="tick"
        ><input type="checkbox" bind:checked={drop} {disabled} /> Drop traffic already
        in flight</label
      >
    </section>
    <section class="unit">
      <label class="boundary"
        >Stage boundary<select {disabled} bind:value={boundary}
          ><option value="">Select stage boundary</option>
          {#each [...boundaries.keys()] as name (name)}<option value={name}
              >{name}</option
            >{/each}</select
        ></label
      >
      {#if chosen}<p>{chosen.blocked} of {chosen.total} paths blocked</p>{/if}
      <div class="actions">
        <button
          disabled={disabled || !chosen || chosen.blocked === chosen.total}
          onclick={() => changeRoute('boundary', true, boundary)}
          >Block boundary</button
        >
        <button
          disabled={disabled || !chosen || chosen.blocked === 0}
          onclick={() => changeRoute('boundary', false, boundary)}
          >Restore boundary</button
        >
      </div>
    </section>
  </div>
  <div role="status" aria-live="polite" aria-atomic="true">
    {#if receipt && receipt.epoch === lab.epoch && receipt.simulation === lab.simulation_id}
      <p
        class:error={receipt.status === 'Rejected' ||
          receipt.status === 'Unconfirmed'}
      >
        <strong>{receipt.status}</strong> · {receipt.message}
      </p>
    {/if}
  </div>
</section>

<style>
  .interventions {
    min-width: 0;
    width: 100%;
    box-sizing: border-box;
    padding: 0.65rem 0.85rem;
    border-top: 1px solid var(--border, #c9d1cc);
    color: var(--text, #1c2b24);
    background: var(--panel, #fff);
    font-size: 0.84rem;
  }
  header,
  .actions {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    flex-wrap: wrap;
  }
  header {
    justify-content: space-between;
  }
  h2,
  h3,
  p {
    margin: 0;
  }
  h2 {
    font-size: 0.9rem;
  }
  h3 {
    font-size: 0.84rem;
  }
  .controls {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 12rem), 1fr));
    align-items: start;
    gap: 0.65rem 0.85rem;
    margin-top: 0.5rem;
  }
  .unit {
    min-width: 0;
  }
  .availability {
    border: 1px solid var(--border, #c9d1cc);
    border-radius: 0.4rem;
    padding: 0.45rem 0.6rem;
    background: white;
  }
  .node-summary {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin: 0.4rem 0;
  }
  .node-summary span {
    display: block;
    color: var(--muted, #495a51);
    font-size: 0.76rem;
  }
  button.offline {
    background: #a32c30;
    color: #fff;
    border-color: #902328;
  }
  button.offline:hover:enabled {
    background: #862126;
  }
  .unit p {
    margin: 0.35rem 0 0.45rem;
    color: var(--muted, #495a51);
    overflow-wrap: anywhere;
  }
  strong {
    color: var(--text, #1c2b24);
  }
  button {
    font: inherit;
    font-weight: 550;
    min-height: 2.1rem;
    padding: 0.35rem 0.55rem;
  }
  label.boundary {
    display: grid;
    gap: 0.2rem;
    margin: 0 0 0.35rem;
    font-weight: 550;
  }
  select {
    width: 100%;
    box-sizing: border-box;
  }
  .tick {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    margin: 0.5rem 0 0;
    font-size: 0.78rem;
  }
  .error,
  .error strong {
    color: #91371e;
  }
  [role='status'] p {
    margin-top: 0.7rem;
    padding-top: 0.5rem;
    border-top: 1px solid var(--border, #c9d1cc);
  }
</style>
