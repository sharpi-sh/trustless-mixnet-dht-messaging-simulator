<script lang="ts">
  import { onDestroy } from 'svelte';
  import { SvelteMap } from 'svelte/reactivity';
  import type { Message } from './types';

  let {
    messages,
    save,
    onDirty,
    busy,
  }: {
    messages: Message[];
    save: (updates: Record<string, string>) => Promise<unknown>;
    onDirty: (dirty: boolean) => void;
    busy: boolean;
  } = $props();
  let edits = $state<Record<string, string>>({});
  let saving = $state(false);
  let error = $state('');
  let groups = $derived.by(() => {
    const grouped = new SvelteMap<string, Message[]>();
    for (const message of messages) {
      const key = `${message.sender_id} · ${message.conversation_id}`;
      const entries = grouped.get(key) ?? [];
      entries.push(message);
      grouped.set(key, entries);
    }
    return Array.from(grouped);
  });
  let changes = $derived(
    Object.fromEntries(
      messages
        .filter(
          (m) => edits[m.id] !== undefined && edits[m.id] !== (m.text ?? ''),
        )
        .map((m) => [m.id, edits[m.id]]),
    ),
  );
  let dirty = $derived(Object.keys(changes).length > 0);
  let valid = $derived(
    Object.values(changes).every((text) => text.trim().length > 0),
  );
  $effect(() => {
    for (const message of messages) {
      if (edits[message.id] !== undefined && edits[message.id] === message.text)
        delete edits[message.id];
    }
    onDirty(dirty);
  });
  onDestroy(() => {
    onDirty(false);
  });

  function change(message: Message, value: string) {
    if (value === (message.text ?? '')) delete edits[message.id];
    else edits[message.id] = value;
    error = '';
  }

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    if (!dirty || !valid || busy || saving) return;
    saving = true;
    error = '';
    try {
      await save({ ...changes });
      // The next authoritative staged-message update releases the dirty flag.
    } catch (cause) {
      error =
        cause instanceof Error
          ? cause.message
          : 'The backend could not save the messages.';
    } finally {
      saving = false;
    }
  }
</script>

<form onsubmit={submit} aria-label="Staged messages" class="editor">
  <header>
    <h2>Staged messages</h2>
    <span>{messages.length} transmissions</span>
  </header>
  <div class="groups">
    {#each groups as [group, entries] (group)}
      <fieldset disabled={saving || busy}>
        <legend>{group}</legend>
        {#each entries as message (message.id)}
          <label>
            <span
              >Exchange {message.exchange} · {message.direction === 'reply'
                ? 'Reply'
                : 'Message'} to {message.target_id}</span
            >
            <textarea
              aria-label={`Message text ${message.id}`}
              rows="2"
              required
              value={edits[message.id] ?? message.text ?? ''}
              oninput={(event) => change(message, event.currentTarget.value)}
            ></textarea>
          </label>
        {/each}
      </fieldset>
    {/each}
  </div>
  {#if dirty && !valid}<p role="alert">Each message needs visible text.</p>{/if}
  {#if error}<p role="alert">{error}</p>{/if}
  <footer>
    <span aria-live="polite">{dirty ? 'Unsaved changes' : ''}</span><button
      disabled={!dirty || !valid || saving || busy}
      type="submit">{saving ? 'Saving…' : 'Save messages'}</button
    >
  </footer>
</form>

<style>
  .editor {
    color: var(--text, #202b31);
  }
  header,
  footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.7rem;
  }
  h2 {
    margin: 0;
    font-size: 1rem;
  }
  header > span,
  footer > span {
    font-size: 0.78rem;
    color: var(--muted, #46565f);
  }
  .groups {
    max-height: 27rem;
    overflow-y: auto;
    scrollbar-gutter: stable;
    margin: 0.5rem 0;
  }
  fieldset {
    min-width: 0;
    border: 0;
    border-top: 1px solid var(--border, #bac6cc);
    padding: 0.5rem 0;
    margin: 0 0 0.4rem;
  }
  legend {
    font-size: 0.8rem;
    font-weight: 650;
    padding: 0 0.5rem 0 0;
  }
  label {
    display: grid;
    gap: 0.24rem;
    margin: 0.25rem 0 0.55rem;
  }
  label span {
    font-size: 0.75rem;
    color: var(--muted, #46565f);
  }
  textarea {
    box-sizing: border-box;
    width: 100%;
    max-width: 100%;
    min-height: 3rem;
    resize: vertical;
    border: 1px solid var(--border, #a7b4ba);
    border-radius: 0.28rem;
    background: var(--panel, #fff);
    color: inherit;
    padding: 0.45rem 0.55rem;
    font: inherit;
    font-size: 0.85rem;
  }
  button {
    min-height: 2.35rem;
    padding: 0.4rem 0.7rem;
    border: 1px solid var(--border, #a7b4ba);
    border-radius: 0.3rem;
    background: var(--panel, #fff);
    color: inherit;
    font: inherit;
    font-size: 0.84rem;
    font-weight: 600;
    cursor: pointer;
  }
  button:disabled {
    opacity: 0.55;
    cursor: default;
  }
  textarea:focus-visible,
  button:focus-visible {
    outline: 2px solid var(--accent, #17583f);
    outline-offset: 2px;
  }
  [role='alert'] {
    font-size: 0.82rem;
    color: #8e301d;
  }
</style>
