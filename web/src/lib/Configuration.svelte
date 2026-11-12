<script lang="ts">
  import { avatarUrl } from './avatars';
  import { channelNames } from './channels';
  import FieldHelp from './FieldHelp.svelte';
  import { untrack } from 'svelte';
  import type { Channel, Config } from './types';
  import {
    configurationError,
    conversationCount,
    fieldHelp,
    loopixFields,
    outageFields,
    pollingFields,
    participantIds,
    prepareConfig,
    storageFields,
    transportFields,
    type NumericField,
  } from './configuration';

  let {
    defaults,
    participantLabels = {},
    create,
    busy,
  }: {
    defaults: Config;
    participantLabels?: Record<string, string>;
    create: (cfg: Config) => Promise<unknown>;
    busy: boolean;
  } = $props();
  let cfg = $state<Config>(untrack(() => JSON.parse(JSON.stringify(defaults))));
  let submitting = $state(false);
  let error = $state('');
  let receivers = $derived(participantIds('receiver', cfg.receiver_count));
  let senders = $derived(participantIds('sender', cfg.sender_count));
  let conversations = $derived(conversationCount(cfg));
  let transmissions = $derived(conversations * cfg.exchanges * 2);

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    if (busy || submitting) return;
    const ready = prepareConfig($state.snapshot(cfg));
    error = configurationError(ready);
    if (error) return;
    submitting = true;
    try {
      await create(ready);
    } catch (cause) {
      error =
        cause instanceof Error
          ? cause.message
          : 'The backend could not create the simulation.';
    } finally {
      submitting = false;
    }
  }
</script>

{#snippet info(label: string, key: string, uid: string)}
  {label}<FieldHelp {label} text={fieldHelp[key]} {uid} />
{/snippet}

{#snippet numbers(fields: NumericField[])}
  <div class="fields">
    {#each fields as [key, label, min, max, rule] (key)}
      <label
        >{@render info(label, key, key)}<input
          aria-label={label}
          type="number"
          {min}
          {max}
          step={rule === 'positive' || rule === 'decimal' ? 'any' : 1}
          required
          bind:value={cfg[key]}
        /></label
      >
    {/each}
  </div>
{/snippet}

<form
  onsubmit={submit}
  aria-label="Simulation configuration"
  class="configuration"
>
  <fieldset disabled={busy || submitting} class="shell">
    <section aria-labelledby="network-setup-heading">
      <h2 id="network-setup-heading">Network setup</h2>
      {#each ['sender', 'recipient'] as role (role)}
        {@const isSender = role === 'sender'}
        {@const ids = isSender ? senders : receivers}
        {@const countKey = isSender ? 'sender_count' : 'receiver_count'}
        {@const channelKey = isSender ? 'sender_channel' : 'recipient_channel'}
        <fieldset class="participants">
          <legend>{isSender ? 'Senders' : 'Recipients'}</legend>
          {#each ids as id, index (id)}
            {@const name = participantLabels[id] || id}
            <div class="participant">
              <span class="identity"
                ><img
                  src={avatarUrl(id)}
                  alt=""
                  width="32"
                  height="32"
                />{name}</span
              >
              {#if cfg.participant_channels}
                <span class="channel-field">
                  <FieldHelp
                    label={name + ' channel'}
                    text={fieldHelp.participant_channel}
                    uid={'channel-' + id}
                  />
                  <select
                    aria-label={name + ' channel'}
                    value={cfg.participant_channels[id] ??
                      cfg[channelKey] ??
                      'tor'}
                    onchange={(event) => {
                      cfg.participant_channels = {
                        ...cfg.participant_channels,
                        [id]: event.currentTarget.value as Channel,
                      };
                    }}
                  >
                    {#each Object.entries(channelNames) as [value, label] (value)}
                      <option {value}>{label}</option>
                    {/each}
                  </select>
                </span>
              {/if}
              {#if index > 0 && index === ids.length - 1}
                <button
                  type="button"
                  class="secondary remove"
                  aria-label={'Remove ' + name}
                  onclick={() => {
                    if (cfg.participant_channels)
                      delete cfg.participant_channels[id];
                    delete cfg.polling_overrides[id];
                    cfg[countKey]--;
                  }}>Remove</button
                >
              {/if}
            </div>
          {/each}
          {#if !cfg.participant_channels}
            <label>
              {@render info(
                isSender ? 'Sender channel' : 'Recipient channel',
                'participant_channel',
                role + '-channel',
              )}
              {#if cfg[channelKey]}
                <select
                  aria-label={isSender ? 'Sender channel' : 'Recipient channel'}
                  bind:value={cfg[channelKey]}
                >
                  {#each Object.entries(channelNames) as [value, label] (value)}
                    <option {value}>{label}</option>
                  {/each}
                </select>
              {:else}<span>Tor only</span>{/if}
            </label>
          {/if}
          <button
            class="secondary add"
            type="button"
            disabled={ids.length >= 10}
            onclick={() => cfg[countKey]++}>Add another {role}</button
          >
        </fieldset>
      {/each}
      <div class="fields">
        <label
          >{@render info(
            cfg.randomise_count ? 'Minimum mix nodes' : 'Mix nodes',
            'min_nodes',
            'min_nodes',
          )}<input
            aria-label={cfg.randomise_count ? 'Minimum mix nodes' : 'Mix nodes'}
            type="number"
            min="6"
            max="20"
            step="1"
            required
            bind:value={cfg.min_nodes}
          /></label
        >
        {#if cfg.randomise_count}<label
            >{@render info('Maximum mix nodes', 'max_nodes', 'max_nodes')}<input
              aria-label="Maximum mix nodes"
              type="number"
              min="6"
              max="20"
              step="1"
              required
              bind:value={cfg.max_nodes}
            /></label
          >{/if}
      </div>
      <label class="tick"
        ><input
          type="checkbox"
          aria-label="Randomise mix node count"
          bind:checked={cfg.randomise_count}
        /><span
          >{@render info(
            'Randomise mix node count',
            'randomise_count',
            'randomise_count',
          )}</span
        ></label
      >
    </section>
    <div class="settings">
      <section>
        <h2>Conversations</h2>
        <div class="fields">
          <label
            >{@render info(
              'Pairing strategy',
              'pairing_strategy',
              'pairing_strategy',
            )}<select
              aria-label="Pairing strategy"
              bind:value={cfg.pairing_strategy}
            >
              <option value="all_to_one">All senders to one receiver</option
              ><option value="one_to_all">One sender to all receivers</option>
              <option value="one_to_one_pairs">One-to-one pairs</option><option
                value="random_pairs">Random distinct pairs</option
              >
            </select></label
          >
          {#if cfg.pairing_strategy === 'random_pairs'}
            <label
              >{@render info(
                'Random pair count',
                'pair_count',
                'pair_count',
              )}<input
                aria-label="Random pair count"
                type="number"
                min="1"
                max={cfg.sender_count * cfg.receiver_count}
                step="1"
                required
                bind:value={cfg.pair_count}
              /></label
            >
          {/if}
          <label
            >{@render info(
              'Exchanges per conversation',
              'exchanges',
              'exchanges',
            )}<input
              aria-label="Exchanges per conversation"
              type="number"
              min="1"
              max="10"
              step="1"
              required
              bind:value={cfg.exchanges}
            /></label
          >
        </div>
        <p class="estimate">
          {conversations || 0}
          {conversations === 1 ? 'conversation' : 'conversations'} ·
          <strong>{transmissions || 0} transmissions</strong> including replies
        </p>
      </section>
      <section>
        <h2>Run settings</h2>
        <div class="fields">
          <label
            >{@render info('Random seed', 'random_seed', 'random_seed')}<input
              aria-label="Random seed"
              type="number"
              min="0"
              max={Number.MAX_SAFE_INTEGER}
              step="1"
              placeholder="Generated by Python"
              bind:value={cfg.random_seed}
            /></label
          >
          <label
            >{@render info(
              'Playback delay (ms)',
              'step_delay_ms',
              'step_delay_ms',
            )}<input
              aria-label="Playback delay (ms)"
              type="number"
              min="0"
              max="2000"
              required
              bind:value={cfg.step_delay_ms}
            /></label
          >
          <label
            >{@render info('Node availability', 'pattern', 'pattern')}<select
              aria-label="Node availability"
              bind:value={cfg.pattern}
            >
              <option value="always_online">Always online</option><option
                value="always_offline">Always offline</option
              >
              <option value="random">Random outages</option><option
                value="bursty">Bursty outages</option
              ><option value="scheduled">Scheduled outages</option>
            </select></label
          >
        </div>
        {#if cfg.pattern === 'scheduled'}
          <div class="schedule">
            <h3>Scheduled outages</h3>
            {#each cfg.scheduled_outages as row, index (row)}
              <div class="outage">
                <label
                  >{@render info(
                    'Node ID',
                    'outage_node',
                    `outage-node-${index}`,
                  )}<input
                    aria-label="Node ID"
                    required
                    bind:value={row.node_id}
                    placeholder="mix-1"
                  /></label
                >
                <label
                  >{@render info(
                    'Start (ms)',
                    'outage_start',
                    `outage-start-${index}`,
                  )}<input
                    aria-label="Start (ms)"
                    type="number"
                    min="0"
                    step="1"
                    required
                    bind:value={row.start_ms}
                  /></label
                >
                <label
                  >{@render info(
                    'Duration (ms)',
                    'outage_duration',
                    `outage-duration-${index}`,
                  )}<input
                    aria-label="Duration (ms)"
                    type="number"
                    min="0"
                    step="1"
                    required
                    bind:value={row.duration_ms}
                  /></label
                >
                <button
                  class="secondary"
                  type="button"
                  aria-label={`Remove outage ${index + 1}`}
                  onclick={() => cfg.scheduled_outages.splice(index, 1)}
                  >Remove</button
                >
              </div>
            {/each}
            <button
              class="secondary"
              type="button"
              onclick={() =>
                cfg.scheduled_outages.push({
                  node_id: '',
                  start_ms: 0,
                  duration_ms: 1000,
                })}>Add outage</button
            >
          </div>
        {/if}
        <label class="tick"
          ><input
            type="checkbox"
            aria-label="Enable receiver polling"
            bind:checked={cfg.polling_enabled}
          /><span
            >{@render info(
              'Enable receiver polling',
              'polling_enabled',
              'polling_enabled',
            )}</span
          ></label
        >
      </section>
      <details>
        <summary>Advanced settings</summary>
        <div class="advanced">
          <h3>Receiver polling</h3>
          {@render numbers(pollingFields)}
          <div class="fields">
            {#each receivers as uid (uid)}
              <label
                >{@render info(
                  uid,
                  'polling_override',
                  `polling-override-${uid}`,
                )}<select
                  aria-label={`Polling override for ${uid}`}
                  value={cfg.polling_overrides[uid] === undefined
                    ? ''
                    : String(cfg.polling_overrides[uid])}
                  onchange={(event) => {
                    const choice = event.currentTarget.value;
                    if (choice === '') delete cfg.polling_overrides[uid];
                    else cfg.polling_overrides[uid] = choice === 'true';
                  }}
                >
                  <option value="">Use polling default</option><option
                    value="true">Enabled</option
                  ><option value="false">Disabled</option>
                </select></label
              >
            {/each}
          </div>
          <h3>DHT and storage</h3>
          {@render numbers(storageFields)}
          <h3>Path timing and retries</h3>
          {@render numbers(transportFields)}
          <h3>Loopix traffic parameters</h3>
          {@render numbers(loopixFields)}
          <h3>Outage parameters</h3>
          {@render numbers(outageFields)}
        </div>
      </details>
      {#if error}<p role="alert">{error}</p>{/if}
      <div class="actions">
        <button class="primary" type="submit"
          >{submitting ? 'Creating…' : 'Create simulation'}</button
        >
      </div>
    </div>
  </fieldset>
</form>

<style>
  .configuration {
    color: var(--text, #202b31);
    font-size: 0.875rem;
  }
  .shell {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    align-items: start;
    gap: clamp(1.5rem, 3vw, 3rem);
    min-width: 0;
    border: 0;
    padding: 0;
    margin: 0;
  }
  .settings {
    min-width: 0;
  }
  @media (max-width: 48rem) {
    .shell {
      grid-template-columns: minmax(0, 1fr);
      gap: 1rem;
    }
  }
  section,
  details {
    padding: 0.95rem 0;
    border-bottom: 1px solid var(--border, #bac6cc);
  }
  section:first-child {
    padding-top: 0;
  }
  h2,
  h3 {
    margin: 0 0 0.6rem;
    line-height: 1.25;
  }
  h2 {
    font-size: 1.02rem;
  }
  h3 {
    font-size: 0.88rem;
  }
  .participants {
    min-width: 0;
    border: 0;
    margin: 0 0 1rem;
    padding: 0;
  }
  .participants legend {
    padding: 0;
    margin-bottom: 0.35rem;
    font-weight: 650;
  }
  .participant {
    display: grid;
    grid-template-columns: minmax(6.1rem, 1fr) minmax(0, 2fr) 4.5rem;
    align-items: center;
    gap: 0.5rem;
    padding: 0.3rem 0;
  }
  .identity {
    display: flex;
    align-items: center;
    gap: 0.45rem;
  }
  .channel-field {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: center;
    gap: 0.3rem;
  }
  .channel-field select {
    grid-column: 1 / -1;
  }
  .identity img {
    flex: none;
    border-radius: 50%;
    object-fit: cover;
  }
  .participant .remove {
    padding-inline: 0.3rem;
  }
  .add {
    margin-top: 0.35rem;
  }
  .add:disabled {
    opacity: 0.55;
  }
  .fields,
  .outage {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 9.5rem), 1fr));
    gap: 0.7rem 0.85rem;
  }
  label {
    display: grid;
    gap: 0.25rem;
    font-weight: 550;
    font-size: 0.81rem;
    color: var(--text, #202b31);
  }
  input,
  select,
  button {
    font: inherit;
  }
  input,
  select {
    height: 2.45rem;
    box-sizing: border-box;
    min-width: 0;
    width: 100%;
    border: 1px solid var(--border, #a7b4ba);
    border-radius: 0.28rem;
    background: var(--panel, #fff);
    color: inherit;
    padding: 0 0.55rem;
  }
  .tick {
    display: flex;
    align-items: center;
    gap: 0.45rem;
    margin-top: 0.7rem;
    font-weight: 450;
  }
  .tick input {
    height: 1rem;
    width: 1rem;
    margin: 0;
    accent-color: var(--accent, #12654c);
  }
  .estimate {
    font-size: 0.82rem;
    margin: 0.65rem 0 0;
    color: var(--muted, #46565f);
  }
  .estimate strong {
    color: var(--text, #202b31);
  }
  summary {
    cursor: pointer;
    font-weight: 650;
  }
  .advanced,
  .schedule {
    padding: 0.8rem 0 0;
  }
  .advanced .fields + .fields {
    margin-top: 0.7rem;
  }
  .advanced h3:not(:first-child) {
    margin-top: 1.15rem;
  }
  .outage {
    align-items: end;
    margin-bottom: 0.7rem;
  }
  button {
    border: 1px solid var(--border, #a7b4ba);
    border-radius: 0.3rem;
    cursor: pointer;
    padding: 0.5rem 0.85rem;
    min-height: 2.4rem;
    font-weight: 600;
  }
  .primary {
    background: var(--accent, #17583f);
    color: #fff;
    border-color: transparent;
  }
  .secondary {
    background: var(--panel, #fff);
    color: var(--text, #202b31);
  }
  :disabled {
    cursor: default;
  }
  .actions {
    display: flex;
    justify-content: flex-end;
    margin-top: 0.85rem;
  }
  [role='alert'] {
    color: #8e301d;
  }
  input:focus-visible,
  select:focus-visible,
  button:focus-visible,
  summary:focus-visible {
    outline: 2px solid var(--accent, #17583f);
    outline-offset: 2px;
  }
</style>
