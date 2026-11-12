<script lang="ts">
  import { untrack } from 'svelte';
  import type { Snapshot } from './types';
  import { time } from './inspector';
  let { lab, onNode }: { lab: Snapshot; onNode: (id: string) => void } =
    $props();
  let id = $state(untrack(() => lab.messages[0]?.id ?? ''));
  let rows = $derived(lab.lineage.filter((row) => row.message_id === id));
  let message = $derived(lab.messages.find((m) => m.id === id));
  let names = $derived(new Map(lab.devices.map((p) => [p.id, p.label])));
</script>

<section class="records" aria-labelledby="lineage-heading">
  <div class="record-head">
    <h2 id="lineage-heading">Cryptographic lineage</h2>
    <label
      >Lineage message<select bind:value={id}
        >{#each lab.messages as m (m.id)}<option value={m.id}
            >{m.id} · {m.direction}</option
          >{/each}</select
      ></label
    >
  </div>
  {#if message}<p class="record-lead">
      {names.get(message.sender_id)} → {names.get(message.target_id)} · {message.conversation_id}
      · {lab.outcomes[message.id]}
    </p>{/if}
  {#if rows.length}<div class="record-scroll">
      <table>
        <thead
          ><tr
            ><th>Logical time</th><th>Operation</th><th>Location</th><th
              >Artefact</th
            ><th>Container</th></tr
          ></thead
        ><tbody>
          {#each rows as row, i (i)}<tr
              ><td>{time(row.simulation_time_ms)}</td><td
                >{row.detail}<small>{row.operation}</small></td
              ><td
                ><button
                  class="record-link"
                  onclick={() => onNode(row.location)}>{row.location}</button
                ></td
              ><td><code>{row.artefact}</code></td><td
                ><code>{row.container ?? '—'}</code></td
              ></tr
            >{/each}
        </tbody>
      </table>
    </div>{:else}<p class="records-empty">
      No cryptographic operations recorded for this message.
    </p>{/if}
  {#if rows.some((row) => row.operation === 'sender_signature_verified')}
    <p class="record-note">The recipient verified the sender’s signature.</p>
  {:else if rows.some((row) => row.operation === 'reply_key_learned')}
    <p class="record-note">
      A reply key was recorded without sender verification evidence.
    </p>
  {/if}
</section>
