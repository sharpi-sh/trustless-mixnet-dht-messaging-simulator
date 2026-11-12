<script lang="ts">
  import { onMount } from 'svelte';
  import { LabClient } from '../lib/api';
  import Configuration from '../lib/Configuration.svelte';
  import MessageEditor from '../lib/MessageEditor.svelte';
  import type { Config, CommandType } from '../lib/types';
  import Workspace from '../lib/Workspace.svelte';
  import './lab.css';

  const client = new LabClient();
  const store = client.store;
  let endpoint = $state('');
  let mounted = $state(false);
  let tested = $state('');
  let view = $state<'connection' | 'configuration' | 'laboratory'>(
    'connection',
  );
  let dirty = $state(false);
  let lastId = $state('');
  let uiError = $state('');
  let lab = $derived($store.snapshot);
  let pending = $derived($store.pending > 0);
  let connected = $derived($store.connection === 'connected');

  onMount(() => {
    const port = new URLSearchParams(location.search).get('port');
    endpoint =
      port && /^\d+$/.test(port) && +port > 0 && +port <= 65535
        ? port
        : (localStorage.getItem('lab-endpoint') ?? '');
    mounted = true;
    return () => client.disconnect();
  });
  $effect(() => {
    if (lab && lab.simulation_id !== lastId) {
      lastId = lab.simulation_id;
      view = 'laboratory';
    }
  });

  async function act(fn: () => Promise<unknown>) {
    uiError = '';
    try {
      await fn();
    } catch (error) {
      uiError = error instanceof Error ? error.message : String(error);
    }
  }
  async function testEndpoint() {
    tested = '';
    await act(async () => {
      await client.test(endpoint);
      tested = endpoint;
    });
  }
  async function connect() {
    await act(async () => {
      await client.connect();
      localStorage.setItem('lab-endpoint', endpoint);
      view = $store.snapshot ? 'laboratory' : 'configuration';
    });
  }
  async function create(config: Config) {
    await client.create(config);
    dirty = false;
    view = 'laboratory';
  }
  function command(type: CommandType) {
    return act(async () => {
      await client.command(type);
      if (type === 'reset') dirty = false;
    });
  }
</script>

<svelte:head>
  <title>Messaging network laboratory</title>
  <meta
    name="description"
    content="Local simulation console for Loopix routing, Kademlia lookups and encrypted message delivery."
  />
</svelte:head>

<header class="mast">
  <div class="brand">
    <span class="brand-icon" aria-hidden="true"
      ><svg viewBox="0 0 28 28" fill="none"
        ><path
          d="M5 8h12l6 6-6 6H5l6-6-6-6Z"
          stroke="currentColor"
          stroke-width="1.6"
        /><path
          d="m10 8 6 6-6 6"
          stroke="currentColor"
          stroke-width="1.6"
        /></svg
      ></span
    >
    <span>Trustless <strong>Messaging Simulator</strong></span>
  </div>
  <span class="connection-pill" class:live={connected} role="status"
    ><i></i>Backend {$store.connection}</span
  >
</header>
<main>
  <div class="heading">
    <div>
      <h1>Messaging network laboratory</h1>
      <p>
        Inspect source-routed packets, distributed lookups and encrypted message
        delivery.
      </p>
    </div>
    {#if lab}<div class="run-id">
        <small>Simulation ID</small><code>{lab.simulation_id}</code>
      </div>{/if}
  </div>
  <nav class="tabs" aria-label="Laboratory sections">
    <button
      class:active={view === 'connection'}
      onclick={() => (view = 'connection')}>Connection</button
    >
    <button
      disabled={!connected}
      class:active={view === 'configuration'}
      onclick={() => (view = 'configuration')}>Configuration</button
    >
    <button
      disabled={!lab}
      class:active={view === 'laboratory'}
      onclick={() => (view = 'laboratory')}>Laboratory</button
    >
  </nav>

  {#if $store.error || uiError}<p class="error" role="alert">
      {$store.error || uiError}
    </p>{/if}

  {#if connected && !$store.messagePacedPlayback}
    <p class="startup-hint">
      This Python server uses the earlier playback timing. Connect to a server
      started from the updated checkout to follow the first message on Run.
    </p>
  {/if}

  {#if view === 'connection'}
    <section class="connection-grid">
      <div class="panel endpoint-panel">
        <div class="section-icon" aria-hidden="true">
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.7"
            ><rect x="3" y="4" width="18" height="13" rx="2" /><path
              d="M8 21h8m-4-4v4M7 8l3 2-3 2m5 0h4"
            /></svg
          >
        </div>
        <h2>Backend connection</h2>
        <p>Enter the port or local URL printed by the Python process.</p>
        <label for="endpoint">Backend endpoint</label>
        <input
          disabled={!mounted}
          id="endpoint"
          type="text"
          bind:value={endpoint}
          placeholder="Port or local HTTP URL"
          spellcheck="false"
          autocomplete="off"
          oninput={() => {
            tested = '';
            uiError = '';
          }}
        />
        <div class="button-row">
          <button
            class="action"
            disabled={!endpoint.trim() || $store.connection === 'testing'}
            onclick={testEndpoint}>Test connection</button
          >
          {#if connected}
            <button
              onclick={() => {
                client.disconnect();
                tested = '';
              }}>Disconnect</button
            >
            <button
              onclick={() => (view = lab ? 'laboratory' : 'configuration')}
              >Continue</button
            >
          {:else}
            <button
              disabled={!tested ||
                tested !== endpoint ||
                $store.connection === 'connecting'}
              onclick={connect}>Connect</button
            >
          {/if}
        </div>
        {#if $store.http}
          <dl class="endpoint-list">
            <dt>HTTP</dt>
            <dd>{$store.http}</dd>
            <dt>WebSocket</dt>
            <dd>{$store.ws}</dd>
            {#if $store.version}<dt>API version</dt>
              <dd>{$store.version}</dd>{/if}
          </dl>
        {/if}
      </div>
      <aside class="startup">
        <h2>Local processes</h2>
        <div class="process">
          <div>
            <span class="terminal-icon" aria-hidden="true">›_</span><strong
              >Simulation engine</strong
            >
          </div>
          <p>
            From the repository root, activate the Python environment and start
            the engine.
          </p>
          <pre><code>python python/main.py</code></pre>
        </div>
        <div class="process">
          <div>
            <span class="terminal-icon" aria-hidden="true">›_</span><strong
              >Web client</strong
            >
          </div>
          <p>Run the client in a second terminal.</p>
          <pre><code
              >cd web
npm run dev</code
            ></pre>
        </div>
      </aside>
    </section>
  {:else if view === 'configuration' && $store.config}
    <Configuration
      defaults={$store.config}
      {create}
      busy={pending || !connected}
    />
  {:else if lab}
    <section class="lab-workspace">
      <div class="controls panel">
        <div class="clock">
          <span class="state-dot" class:running={lab.status === 'running'}
          ></span><strong>{lab.status}</strong>
          <code>{(lab.simulation_time_ms / 1000).toFixed(3)} s</code>
        </div>
        <div class="button-row run-controls">
          <button
            class="action"
            disabled={!connected || pending || dirty || lab.status !== 'ready'}
            onclick={() => command('run')}>Run</button
          >
          <button
            disabled={!connected || pending || lab.status !== 'running'}
            onclick={() => command('pause')}>Pause</button
          >
          <button
            disabled={!connected || pending || lab.status !== 'paused'}
            onclick={() => command('resume')}>Resume</button
          >
          <button
            disabled={!connected ||
              pending ||
              dirty ||
              !['ready', 'paused'].includes(lab.status)}
            onclick={() => command('step')}>Step</button
          >
          {#if lab.first_message_hop_sequence === null}
            <button
              disabled={!connected ||
                pending ||
                dirty ||
                !['ready', 'paused'].includes(lab.status)}
              aria-describedby="first-message-help"
              onclick={() => command('step_to_first_message_hop')}
            >
              Step to first message hop
            </button>
          {/if}
          <button
            disabled={!connected ||
              pending ||
              !['running', 'paused'].includes(lab.status)}
            onclick={() => command('stop')}>Stop</button
          >
          <button
            disabled={!connected || pending}
            onclick={() => command('reset')}>Reset</button
          >
        </div>
        <label class="pacing"
          >Playback delay <output>{lab.step_delay_ms} ms</output>
          <input
            aria-label="Playback delay"
            type="range"
            min="0"
            max="2000"
            step="1"
            value={lab.step_delay_ms}
            disabled={!connected}
            onchange={(e) =>
              act(() =>
                client.command('set_playback_delay', {
                  delay_ms: Number(e.currentTarget.value),
                }),
              )}
          />
        </label>
      </div>
      {#if lab.first_message_hop_sequence === null}
        <p id="first-message-help" class="startup-hint">
          Run follows the message from its first hop to Tor. Choose Step to
          first message hop to pause at departure.
          {#if lab.status === 'paused' && $store.events.at(-1)?.event_type === 'first_message_hop_step_finished'}
            The step limit was reached. Use the control again to continue.
          {/if}
        </p>
      {/if}
      <div class="summary-strip">
        <span>Seed <b>{lab.random_seed}</b></span><span
          >Devices <b>{lab.devices.length}</b></span
        >
        <span
          >Mix nodes <b
            >{lab.topology.nodes.filter((n) => n.kind === 'mix').length}</b
          ></span
        >
        <span>Planned messages <b>{lab.messages.length}</b></span>
      </div>
      {#key lab.simulation_id + ':' + lab.epoch}
        <Workspace {lab} {client} events={$store.events} {connected} />
      {/key}
      {#if lab.status === 'ready'}
        {#key lab.simulation_id + ':' + lab.epoch}
          <MessageEditor
            messages={lab.messages}
            busy={pending || !connected}
            onDirty={(v) => (dirty = v)}
            save={(updates) =>
              client.command('set_staged_messages', { messages: updates })}
          />
        {/key}
      {/if}
      <p class="command-feedback" aria-live="polite">
        {pending ? 'Applying command…' : $store.feedback}
      </p>
    </section>
  {/if}
  <footer>
    <span>Local simulation</span><span
      >Tor abstraction · Loopix 2017 · Kademlia 2002 · Replicated chunk storage</span
    >
  </footer>
</main>

<style>
  .startup-hint {
    margin: 0.35rem 0 0.5rem;
    font-size: 0.8rem;
    color: var(--muted);
  }
</style>
