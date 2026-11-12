<script lang="ts">
  import { tick, untrack } from 'svelte';
  import { SvelteMap } from 'svelte/reactivity';
  import {
    chatRows,
    lastActivity,
    logicalStamp,
    verifiedSigner,
  } from './conversation';
  import SignatureReceipt from './SignatureReceipt.svelte';
  import { messageColour } from './graph-layout';
  import type { Device, Message } from './types';

  let {
    role,
    devices,
    messages,
    selectedId,
    address,
  }: {
    role: Device['role'];
    devices: Device[];
    messages: Message[];
    selectedId?: string;
    address?: string;
  } = $props();
  const title = $derived(
    role === 'sender' ? 'Sender conversations' : 'Recipient conversations',
  );
  let thread = $state('');
  let entries = $state<HTMLElement>(),
    following = true;
  const choices = $derived(devices.filter((d) => d.role === role));
  const person = $derived(
    choices.find((d) => d.id === selectedId) ?? choices[0],
  );
  const names = $derived(new Map(devices.map((d) => [d.id, d.label])));
  const conversations = $derived.by(() => {
    const peers = new SvelteMap<string, string>();
    for (const m of messages) {
      if (m.sender_id === person?.id) peers.set(m.conversation_id, m.target_id);
      else if (m.target_id === person?.id)
        peers.set(m.conversation_id, m.sender_id);
    }
    return peers;
  });
  const rows = $derived(
    chatRows(person?.logs ?? []).filter(
      (r) => !thread || r.conversation_id === thread,
    ),
  );
  const times = $derived(lastActivity(person?.logs ?? []));
  $effect(() => {
    const list = entries,
      count = rows.length,
      owner = person?.id,
      conversation = thread;
    if (list && untrack(() => following)) {
      void tick().then(() => {
        if (
          list === entries &&
          count === rows.length &&
          owner === person?.id &&
          conversation === thread
        )
          list.scrollTop = list.scrollHeight;
      });
    }
  });
</script>

<aside class="chat" aria-label={title}>
  <header>
    <h3>{title}</h3>
    {#if person}
      <strong data-chat-owner={person.id}>{person.label}</strong>
      {#if address}<small data-device-ip={address}>{address}</small>{/if}
      <dl class="activity">
        <dt>Last sent</dt>
        <dd data-last-sent={times.sent ?? ''}>
          {times.sent === null ? '—' : logicalStamp(times.sent)}
        </dd>
        <dt>Last received</dt>
        <dd data-last-received={times.received ?? ''}>
          {times.received === null ? '—' : logicalStamp(times.received)}
        </dd>
      </dl>
    {/if}
    {#if conversations.size > 1}
      <select
        class="thread"
        aria-label={role === 'sender' ? 'Sender thread' : 'Recipient thread'}
        bind:value={thread}
        onchange={() => (following = true)}
      >
        <option value="">All conversations</option
        >{#each conversations as [conv, peer] (conv)}<option value={conv}
            >With {names.get(peer) ?? peer}</option
          >{/each}
      </select>
    {:else if conversations.size}<small
        >With {names.get([...conversations.values()][0])}</small
      >{/if}
  </header>
  <div
    class="messages"
    bind:this={entries}
    onscroll={(e) => {
      const el = e.currentTarget;
      following = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
    }}
  >
    {#if rows.length}
      <ol aria-label={person.label + ' chat messages'}>
        {#each rows as row (row.message_id)}
          {@const own = row.state !== 'received'}
          {@const signer = verifiedSigner(row)}
          <li
            class:outgoing={own}
            data-message-id={row.message_id}
            data-side={own ? 'outgoing' : 'incoming'}
            style:--message-colour={messageColour(row.message_id)}
          >
            <div class="bubble">
              <div class="author">
                <i></i>{own
                  ? 'You'
                  : signer
                    ? (names.get(signer) ?? signer)
                    : 'Unverified sender'}
              </div>
              <p>{row.text}</p>
              {#if !own}<SignatureReceipt {row} />{/if}
            </div>
            <time title={row.simulation_time_ms + ' ms'}
              >{logicalStamp(row.simulation_time_ms)}</time
            >
          </li>
        {/each}
      </ol>
    {:else}<p class="empty">No messages yet.</p>{/if}
  </div>
</aside>

<style>
  .chat {
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
    background: #fcfdfb;
    color: var(--text);
  }
  header {
    display: grid;
    gap: 4px;
    align-content: start;
    padding: 13px 12px 10px;
    border-bottom: 1px solid var(--border);
    background: #fff;
  }
  h3 {
    font-size: 0.72rem;
    line-height: 1.3;
    font-weight: 600;
    color: var(--muted);
    letter-spacing: 0;
  }
  header strong,
  header select {
    font:
      650 1rem/1.35 Inter,
      Arial,
      sans-serif;
    letter-spacing: -0.025em;
  }
  header select {
    width: 100%;
    border: 0;
    background: transparent;
    padding: 0.05rem 0;
    color: var(--text);
    cursor: pointer;
  }
  small,
  header select.thread {
    font:
      0.72rem/1.45 Inter,
      Arial,
      sans-serif;
    color: var(--muted);
    letter-spacing: 0;
  }
  .activity {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 2px 6px;
    margin: 2px 0;
    font: 10px/1.4 var(--mono, monospace);
    color: #506556;
  }
  .activity dd {
    margin: 0;
    text-align: right;
  }
  .messages {
    padding: 12px 9px;
    flex: 1;
    min-height: 0;
    overflow: auto;
    overscroll-behavior: contain;
    scrollbar-width: thin;
  }
  ol {
    margin: 0;
    padding: 0;
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  li {
    display: flex;
    align-items: flex-start;
    flex-direction: column;
    gap: 3px;
    max-width: 93%;
  }
  li.outgoing {
    align-self: flex-end;
    align-items: flex-end;
  }
  .bubble {
    background: #edf0ec;
    border-radius: 10px 10px 10px 2px;
    padding: 8px 9px;
    min-width: 48px;
    text-align: left;
    width: fit-content;
  }
  .outgoing .bubble {
    background: #e1efe4;
    border-radius: 10px 10px 2px 10px;
  }
  .author {
    font-size: 0.65rem;
    color: #506556;
    display: flex;
    align-items: center;
    gap: 4px;
    margin-bottom: 3px;
    font-weight: 650;
  }
  .author i {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--message-colour);
    flex: none;
  }
  p {
    margin: 0;
    font-size: 0.77rem;
    line-height: 1.4;
    overflow-wrap: anywhere;
    white-space: pre-wrap;
  }
  time {
    font: 9px/1.3 var(--mono, monospace);
    color: #607065;
  }
  .empty {
    color: var(--muted);
    font-size: 0.74rem;
  }
</style>
