<script lang="ts">
  import type { Snapshot, NodeDetails, LabEvent, Json } from './types';
  import { display, time, fields, rows, peerPath, relevant } from './inspector';
  let {
    lab,
    details,
    selectedNode,
    selectedPath,
    events,
    onPeer,
    onNode,
    onPath,
  }: {
    lab: Snapshot;
    details: NodeDetails | null;
    selectedNode: string;
    selectedPath: string;
    events: LabEvent[];
    onPeer: (id: string, pathId: string) => void;
    onNode: (id: string) => void;
    onPath: (id: string) => void;
  } = $props();
  const components = {
    person:
      'A simulated handset or computer running the messaging client. It holds the device’s private key, encrypts outgoing text and decrypts incoming messages. The enclosed public key lets the recipient encrypt a reply. Its owner is unverified.',
    tor: 'A model of the Tor connection used by one device. It represents client and relay software as one boundary. Provider polling, DHT queries and vault downloads pass through it. Direct vault reads expose retrieval timing outside the mixnet.',
    provider:
      'A simulated server running a Loopix provider. It accepts Sphinx packets from its clients, forwards them to the first mix layer, and holds mailbox handles for periodic collection. At egress it hands the encrypted bundle to the storage gateway.',
    mix: 'A simulated relay server running a Loopix mix. It checks the packet and replay tag, removes one Sphinx layer, waits for the encoded delay and forwards to the encoded next hop.',
    dht: 'A simulated server running a Kademlia peer. Its local routing table guides XOR-distance lookups for encrypted manifests. Peers exchange bootstrap traffic as soon as the network starts.',
    storage:
      'A simulated storage server running a vault service. It keeps encrypted fragments and serves replicas by identifier. The vault can observe request times, sizes and repeated reads.',
  };
  const tabs = ['Protocol state', 'Activity', 'Lineage'] as const;
  let tab = $state<(typeof tabs)[number]>('Protocol state');
  let pageSize = $state(25);
  let node = $derived(lab.topology.nodes.find((n) => n.id === selectedNode));
  let path = $derived(
    !node ? lab.topology.paths.find((p) => p.id === selectedPath) : undefined,
  );
  let offlineEndpoint = $derived(
    path &&
      lab.topology.nodes.find(
        (n) =>
          !n.online && (n.id === path?.source_id || n.id === path?.target_id),
      ),
  );
  let info = $derived(node && details?.node.id === node.id ? details : null);
  let protocolState = $derived(info?.state ?? {});
  let device = $derived(lab.devices.find((d) => d.id === node?.id));
  let connected = $derived(
    node
      ? lab.topology.paths.filter(
          (p) => p.source_id === node?.id || p.target_id === node?.id,
        )
      : [],
  );
  let transits = $derived(
    connected.flatMap((p) =>
      Object.entries(p.active).map(([id, t]) => ({ id, path: p.id, ...t })),
    ),
  );
  let history = $derived(relevant(events, node?.id ?? '', path));
  let lineage = $derived(
    node
      ? lab.lineage
          .filter((row) => row.location === node?.id)
          .slice()
          .reverse()
      : [],
  );
  let tabId = $props.id();
  let metadataOpen = $state(false);
  function highlight(id: string) {
    if (!node) return;
    const actual = peerPath(connected, node.id, id);
    if (actual) onPeer(id, actual);
    else onNode(id);
  }
  function keys(event: KeyboardEvent, index: number) {
    const direction =
      event.key === 'ArrowLeft' ? -1 : event.key === 'ArrowRight' ? 1 : 0;
    if (!direction && !['Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const target =
      event.key === 'Home'
        ? 0
        : event.key === 'End'
          ? tabs.length - 1
          : (index + direction + tabs.length) % tabs.length;
    tab = tabs[target];
    document.getElementById(tabId + '-tab-' + target)?.focus();
  }
  function label(k: string) {
    return k.replaceAll('_', ' ');
  }
</script>

{#snippet datum(name: string, value: Json | undefined, mono = false)}
  <div>
    <dt>{name}</dt>
    <dd class:mono>{display(value)}</dd>
  </div>
{/snippet}
{#snippet activity()}
  <h3>Event history</h3>
  {#if history.length}
    <ol class="ledger">
      {#each history.slice(0, pageSize) as e (e.event_id)}
        <li>
          <span class="mono">{time(e.simulation_time_ms)}</span>
          <div>
            <b>{label(e.event_type)}</b><small
              >{[e.source_id, e.target_id]
                .filter(Boolean)
                .join(' → ')}{e.message_id ? ' · ' + e.message_id : ''}</small
            >
          </div>
        </li>
      {/each}
    </ol>
    {#if history.length > pageSize}<button onclick={() => (pageSize += 50)}
        >Show earlier events</button
      >{/if}
  {:else}<p class="empty">No events recorded for this selection.</p>{/if}
{/snippet}

{#if node}
  <aside class="inspect" aria-label="Node inspector">
    <header>
      <div>
        <small>{node.stage}</small>
        <h2>{node.label}</h2>
      </div>
      <span class:offline={!node.online} class="status"
        >{node.online ? 'Online' : 'Offline'}</span
      >
    </header>
    <p>{components[node.kind]}</p>
    {#if node.kind === 'provider'}<p>
        {node.id === 'provider-west'
          ? 'West serves the sender devices.'
          : 'East serves the recipient devices.'} The names indicate diagram positions.
        Each side has one provider, so an outage interrupts that side until recovery.
      </p>{/if}
    <dl class="facts">
      {@render datum('Node ID', node.id, true)}{@render datum(
        'Address',
        node.simulated_address,
        true,
      )}
      {@render datum('Operator', node.operator_id)}{@render datum(
        'Last activity',
        time(node.last_activity),
      )}
    </dl>
    {#if info}<p class="profile">
        {info.profile.name}
        <a
          href={'#' + tabId + '-algorithm'}
          onclick={() => (metadataOpen = true)}
          ><code>{info.profile.id}</code></a
        >
      </p>{/if}
    <div class="tabs" role="tablist" aria-label="Node details">
      {#each tabs as t, i (t)}
        <button
          role="tab"
          id={tabId + '-tab-' + i}
          aria-selected={tab === t}
          tabindex={tab === t ? 0 : -1}
          aria-controls={tabId + '-panel'}
          onclick={() => (tab = t)}
          onkeydown={(e) => keys(e, i)}>{t}</button
        >
      {/each}
    </div>
    <div
      role="tabpanel"
      tabindex="0"
      aria-labelledby={tabId + '-tab-' + tabs.indexOf(tab)}
      id={tabId + '-panel'}
    >
      {#if tab === 'Activity'}
        <h3>Availability history</h3>
        <dl class="facts">
          {@render datum('Failures', node.failure_count)}{@render datum(
            'Last transition',
            time(node.history.at(-1)?.[0]),
          )}
        </dl>
        {#each node.history.slice().reverse() as change, i (i)}<p class="line">
            <time>{time(change[0])}</time>
            {change[1] ? 'Online' : 'Offline'}
          </p>{:else}<p class="empty">No status changes recorded.</p>{/each}
        {@render activity()}
      {:else if tab === 'Lineage'}
        <h3>Artefact lineage</h3>
        <ol class="ledger">
          {#each lineage as row, i (i)}
            <li>
              <span class="mono">{time(row.simulation_time_ms)}</span>
              <div>
                <b>{row.detail}</b><small
                  >{row.message_id} · {label(row.operation)}</small
                ><code>{row.artefact}</code>{#if row.container}<small
                    >Container {row.container}</small
                  >{/if}
              </div>
            </li>
          {:else}<li class="empty">
              No artefacts recorded at this node.
            </li>{/each}
        </ol>
      {:else}
        {#if !info}<p class="empty" role="status">Loading protocol state…</p>
        {:else}
          {#if node.kind === 'mix' || node.kind === 'provider'}
            <dl class="facts">
              {@render datum(
                'Mix delay rate (s⁻¹)',
                protocolState.mu_per_second,
              )}{@render datum('Sphinx replay tags', protocolState.replay_tags)}
              {#if node.kind === 'provider' && protocolState.queued_cells !== undefined}{@render datum(
                  'Queued cells',
                  protocolState.queued_cells,
                )}{/if}
            </dl>
            {#if node.kind === 'mix'}
              <h3>Configured adjacency</h3>
              <div class="scroll">
                <table>
                  <caption>Peer reachability observed by {node.id}</caption
                  ><thead
                    ><tr
                      ><th>Peer / layer</th><th>Observed</th><th
                        >Last contact</th
                      ><th>Failures / successes</th><th>Last failure</th></tr
                    ></thead
                  ><tbody>
                    {#each rows(protocolState.adjacent_peers) as a (a.peer_id)}
                      <tr
                        ><td
                          ><button
                            class="link"
                            aria-label={'Highlight peer ' + a.peer_id}
                            onclick={() => highlight(String(a.peer_id))}
                            >{a.peer_id}</button
                          ><small>{a.stage}</small><small>{a.address}</small
                          ></td
                        ><td>{a.status}</td><td>{time(a.last_contact)}</td><td
                          >{a.failures} / {a.successes}</td
                        ><td>{time(a.last_failure)}</td></tr
                      >
                    {/each}</tbody
                  >
                </table>
              </div>
              <h3>Delayed packets</h3>
              {#each Object.entries(fields(protocolState.delayed_packets)) as [packet, until] (packet)}<p
                  class="line"
                >
                  <code>{packet}</code> releases at {time(until)}
                </p>{:else}<p class="empty">
                  No packets queued for release.
                </p>{/each}
            {/if}
          {:else if node.kind === 'dht'}
            <dl class="facts">
              {@render datum(
                '160-bit node ID',
                protocolState.node_id,
                true,
              )}{@render datum('Bucket size k', protocolState.k)}{@render datum(
                'Lookup concurrency α',
                protocolState.alpha,
              )}
            </dl>
            <h3>Routing buckets</h3>
            {#each rows(protocolState.buckets) as bucket, i (bucket.range_start)}
              <details open={rows(protocolState.buckets).length === 1}>
                <summary
                  >Bucket {i + 1} · {rows(bucket.contacts).length} contacts</summary
                >
                <dl class="facts">
                  {@render datum(
                    'Range start',
                    bucket.range_start,
                    true,
                  )}{@render datum(
                    'Range end',
                    bucket.range_end,
                    true,
                  )}{@render datum(
                    'Last lookup',
                    time(bucket.last_lookup_ms),
                  )}{@render datum('Refresh due', bucket.refresh_due)}
                </dl>
                {#if rows(bucket.contacts).length}<div class="scroll">
                    <table>
                      <caption>Least to most recently seen</caption><thead
                        ><tr
                          ><th>Peer</th><th>XOR distance</th><th>Last seen</th
                          ></tr
                        ></thead
                      ><tbody>
                        {#each rows(bucket.contacts) as c (c.peer)}<tr
                            ><td
                              ><button
                                class="link"
                                aria-label={'Highlight peer ' + c.peer}
                                onclick={() => highlight(String(c.peer))}
                                >{c.peer}</button
                              ></td
                            ><td><code>{c.xor_distance}</code></td><td
                              >{time(c.last_seen_ms)}</td
                            ></tr
                          >{/each}
                      </tbody>
                    </table>
                  </div>{:else}<p class="empty">
                    No contacts in this range.
                  </p>{/if}
              </details>
            {/each}
            <h3>Active lookups</h3>
            {#each rows(protocolState.active_lookups) as lookup (lookup.op_id)}
              <p class="line"><b>{lookup.purpose}</b> · {lookup.op_id}</p>
              <p class="mono">{lookup.key}</p>
              <div class="scroll">
                <table>
                  <caption>Shortlist in XOR distance order</caption><thead
                    ><tr
                      ><th>Peer</th><th>Queried</th><th>Responded</th><th
                        >Timed out</th
                      ><th>Distance</th></tr
                    ></thead
                  ><tbody>
                    {#each rows(lookup.shortlist) as c (c.peer)}<tr
                        ><td
                          ><button
                            class="link"
                            onclick={() => highlight(String(c.peer))}
                            >{c.peer}</button
                          ></td
                        ><td>{display(c.queried)}</td><td
                          >{display(c.responded)}</td
                        ><td>{display(c.timed_out)}</td><td
                          ><code>{c.distance}</code></td
                        ></tr
                      >{/each}
                  </tbody>
                </table>
              </div>
            {:else}<p class="empty">No lookups in progress.</p>{/each}
            {#if Array.isArray(protocolState.record_ids) && protocolState.record_ids.length}<h3
              >
                Stored records
              </h3>
              {#each protocolState.record_ids as id (id)}<p class="mono">
                  {id}
                </p>{/each}{/if}
          {:else if node.kind === 'storage'}
            <dl class="facts">
              {@render datum(
                'Used bytes',
                protocolState.used_bytes,
              )}{@render datum(
                'Capacity (bytes)',
                protocolState.capacity_bytes,
              )}
            </dl>
            <h3>Fragment placements</h3>
            {#each rows(protocolState.fragments) as f (f.id)}
              <details>
                <summary
                  >Fragment {f.index} · {f.placement} · {f.size} bytes</summary
                >
                <dl class="facts">
                  {@render datum('Fragment ID', f.id, true)}{@render datum(
                    'SHA-256',
                    f.digest,
                    true,
                  )}{@render datum('Replicas', f.replicas)}{@render datum(
                    'Integrity',
                    f.integrity,
                  )}{@render datum('Writes', f.write_attempts)}{@render datum(
                    'Retrieval attempts',
                    f.retrieval_attempts,
                  )}{@render datum(
                    'Used in reconstruction',
                    f.used_in_reconstruction,
                  )}{@render datum('Last failure', f.last_failure)}
                </dl>
              </details>
            {:else}<p class="empty">
                No fragments placed at this vault.
              </p>{/each}
          {:else if node.kind === 'tor'}
            <dl class="facts">
              {@render datum('Entries', protocolState.entries)}{@render datum(
                'Exits',
                protocolState.exits,
              )}
            </dl>
            <p>
              Owner <button
                class="link"
                onclick={() => onNode(String(protocolState.owner))}
                >{protocolState.owner}</button
              >
            </p>
          {:else if device}
            <dl class="facts">
              {@render datum(
                'Public key fingerprint',
                device.fingerprint,
                true,
              )}{@render datum('Polling enabled', device.polling_enabled)}
            </dl>
            <p>
              Tor boundary <button
                class="link"
                onclick={() => onNode(device.tor_id)}>{device.tor_id}</button
              >
            </p>
            <h3>Device log</h3>
            <ol class="ledger">
              {#each device.logs.slice().reverse() as row, i (i)}<li>
                  <time>{time(row.simulation_time_ms)}</time>
                  <div>
                    <b>{row.state} · {row.message_id}</b><small
                      >{row.conversation_id} · {row.direction}</small
                    >{#if row.text}<p>{row.text}</p>{/if}
                  </div>
                </li>{:else}<li class="empty">
                  No device activity recorded.
                </li>{/each}
            </ol>
          {/if}
          <h3>Network activity</h3>
          <dl class="facts">
            {@render datum(
              'Inbound transits',
              transits.filter((t) => t.target === node?.id).length,
            )}{@render datum(
              'Outbound transits',
              transits.filter((t) => t.source === node?.id).length,
            )}
            {#if protocolState.inbound_queue !== undefined}{@render datum(
                'Inbound queue',
                protocolState.inbound_queue,
              )}{/if}{#if protocolState.outbound_queue !== undefined}{@render datum(
                'Outbound queue',
                protocolState.outbound_queue,
              )}{/if}
          </dl>
          {#each transits as t (t.id)}<p>
              <button class="link" onclick={() => onPath(t.path)}
                >{t.source} → {t.target}</button
              ><small>{t.token} · {time(t.start_ms)} to {time(t.end_ms)}</small>
            </p>{/each}
        {/if}
      {/if}
    </div>
    {#if info}
      <details id={tabId + '-algorithm'} bind:open={metadataOpen}>
        <summary>Algorithm and parameters</summary>
        <p><b>{info.profile.name}</b></p>
        {#if info.profile.reference}<p>
            <!-- The registry supplies the external paper URL, outside the SvelteKit router. -->
            <!-- eslint-disable-next-line svelte/no-navigation-without-resolve -->
            <a href={info.profile.reference} target="_blank" rel="noreferrer"
              >Reference paper ({info.profile.year})</a
            >
          </p>{/if}
        <dl class="facts">
          {#each Object.entries(info.profile.parameters) as [key, value] (key)}{@render datum(
              label(key),
              value,
            )}{/each}
        </dl>
        {#each info.profile.operations as op (op)}<p>· {op}</p>{/each}
        <h4>Simulation boundaries</h4>
        {#each info.profile.boundaries as limit (limit)}<p>
            {limit}
          </p>{/each}
      </details>{/if}
  </aside>
{:else if path}
  <aside class="inspect" aria-label="Path inspector">
    <header>
      <div>
        <small>Network path</small>
        <h2>{path.transport_label}</h2>
      </div>
      <span class:offline={path.blocked || !!offlineEndpoint} class="status"
        >{path.blocked
          ? 'Blocked'
          : offlineEndpoint
            ? 'Endpoint offline'
            : 'Available'}</span
      >
    </header>
    <p>
      <button class="link" onclick={() => path && onNode(path.source_id)}
        >{path.source_id}</button
      >
      ↔
      <button class="link" onclick={() => path && onNode(path.target_id)}
        >{path.target_id}</button
      >
    </p>
    <dl class="facts">
      {@render datum('Path ID', path.id, true)}{@render datum(
        'Boundary',
        path.boundary,
      )}{@render datum('Path transit delay', time(path.base_transit_delay_ms))}
      {@render datum(
        'Seeded jitter',
        time(path.jitter_min_ms) + ' – ' + time(path.jitter_max_ms),
      )}{@render datum('Blocked at', time(path.blocked_at))}{@render datum(
        'Command ID',
        path.blocked_by,
      )}
      {@render datum('Attempted', path.attempted)}{@render datum(
        'Completed',
        path.completed,
      )}{@render datum('Failed', path.failed)}{@render datum(
        'Dropped',
        path.dropped,
      )}
    </dl>
    <h3>Active transits</h3>
    {#each Object.entries(path.active) as [id, t] (id)}<p class="line">
        <b>{t.source} → {t.target}</b><small
          >{t.token} · {t.lane} · {time(t.start_ms)} to {time(t.end_ms)}</small
        >
      </p>{:else}<p class="empty">No traffic in transit.</p>{/each}
    {@render activity()}
  </aside>
{:else}
  <aside class="inspect" aria-label="Inspector">
    <h2>Inspector</h2>
    <p class="empty">Select a node or path to inspect its state.</p>
  </aside>
{/if}

<style>
  .inspect {
    min-width: 0;
    max-width: 100%;
    font-size: 0.83rem;
    color: var(--text, #202b31);
    overflow-wrap: anywhere;
  }
  header,
  .tabs {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.4rem;
  }
  h2 {
    font-size: 1.04rem;
    margin: 0.1rem 0;
  }
  h3 {
    font-size: 0.9rem;
    margin: 1rem 0 0.4rem;
  }
  h4 {
    font-size: 0.83rem;
    margin: 0.65rem 0 0.3rem;
  }
  p {
    margin: 0.35rem 0;
  }
  .facts {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 8rem), 1fr));
    gap: 0.5rem 0.9rem;
    margin: 0.7rem 0;
  }
  dt,
  small,
  caption,
  .empty {
    color: var(--muted, #46565f);
  }
  dt,
  small,
  caption {
    font-size: 0.73rem;
  }
  dd {
    margin: 0.08rem 0;
    font-weight: 550;
  }
  .mono,
  code,
  time {
    font-family: var(--mono, monospace);
    font-size: 0.76rem;
    overflow-wrap: anywhere;
  }
  small {
    display: block;
  }
  .status {
    font-size: 0.73rem;
    font-weight: 650;
    color: #205339;
    background: #edf4ed;
    border: 1px solid #ccdfce;
    padding: 0.15rem 0.4rem;
    border-radius: 4px;
  }
  .offline {
    background: #fff1e7;
    color: #813816;
    border-color: #ebc9b0;
  }
  .profile {
    padding: 0.5rem 0;
    font-weight: 600;
  }
  .profile code {
    display: block;
    color: var(--muted, #46565f);
    font-weight: 400;
  }
  .tabs {
    justify-content: flex-start;
    gap: 0;
    border-bottom: 1px solid var(--border, #ccd3d0);
    margin: 0.4rem 0 0.65rem;
  }
  .tabs button {
    flex: 1;
    min-height: 2rem;
    padding: 0.35rem 0.22rem;
    border: 0;
    border-bottom: 2px solid transparent;
    background: transparent;
    border-radius: 0;
    color: var(--muted, #46565f);
    font-size: 0.78rem;
  }
  .tabs button[aria-selected='true'] {
    border-color: var(--accent, #205339);
    font-weight: 650;
    color: var(--text, #202b31);
  }
  .scroll {
    overflow-x: auto;
    max-width: 100%;
  }
  table {
    width: 100%;
    font-size: 0.76rem;
    border-collapse: collapse;
  }
  td,
  th {
    text-align: left;
    vertical-align: top;
    border-bottom: 1px solid var(--border, #ccd3d0);
    padding: 0.32rem 0.36rem;
  }
  th {
    font-size: 0.72rem;
  }
  caption {
    text-align: left;
    margin: 0.22rem 0;
  }
  td code {
    display: block;
    min-width: 8rem;
  }
  details {
    border-top: 1px solid var(--border, #ccd3d0);
    padding: 0.48rem 0;
  }
  summary {
    cursor: pointer;
    font-weight: 600;
  }
  .link {
    color: var(--accent, #205339);
    background: none;
    border: 0;
    padding: 0.12rem 0.08rem;
    text-decoration: underline;
    text-underline-offset: 0.16em;
    min-height: 0;
    font: inherit;
  }
  .ledger {
    list-style: none;
    margin: 0.4rem 0;
    padding: 0;
  }
  .ledger li {
    border-top: 1px solid var(--border, #ccd3d0);
    padding: 0.4rem 0;
    display: grid;
    grid-template-columns: 4.6rem minmax(0, 1fr);
    gap: 0.45rem;
  }
  .ledger .empty {
    display: block;
  }
  .empty {
    font-size: 0.78rem;
  }
  .line {
    padding: 0.2rem 0;
  }
</style>
