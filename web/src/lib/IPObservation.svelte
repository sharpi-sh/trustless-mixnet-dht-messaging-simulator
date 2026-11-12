<script lang="ts">
  import type { IPHop, Json } from './types';
  let {
    hop,
    heading,
    proxyEgress,
    observation = 'configured',
  }: {
    hop: IPHop;
    heading: string;
    proxyEgress?: string | null;
    observation?: Json;
  } = $props();
  const observed = $derived(observation === 'received');
  const state = $derived(
    observation === 'configured'
      ? 'Configured projection'
      : observation === 'received'
        ? 'Received by peer'
        : observation === 'in_transit'
          ? 'In transit'
          : observation === 'not_received'
            ? 'Peer did not receive this transit'
            : observation === 'local'
              ? 'Local device handoff'
              : 'Observation status unavailable',
  );
</script>

<section aria-label={heading} class="ip-observation">
  <h4>{heading}</h4>
  <small>{state}</small>
  <dl>
    <div>
      <dt>Source IP</dt>
      <dd>{hop.source_ip}</dd>
    </div>
    <div>
      <dt>Destination IP</dt>
      <dd>{hop.destination_ip}</dd>
    </div>
    <div>
      <dt>{observed ? 'Observer' : 'Receiving endpoint'}</dt>
      <dd>{hop.observer}</dd>
    </div>
    <div>
      <dt>{observed ? 'Observed source IP' : 'Projected source IP'}</dt>
      <dd>{hop.observed_source_ip}</dd>
    </div>
    {#if proxyEgress}<div>
        <dt>Proxy egress IP</dt>
        <dd>{proxyEgress}</dd>
      </div>{/if}
  </dl>
  {#if hop.local || observed}<p>{hop.description}</p>
  {:else}<p><strong>Visibility on delivery</strong> · {hop.description}</p>{/if}
</section>

<style>
  .ip-observation {
    min-width: 0;
    padding: 0.45rem 0;
    font-size: 0.78rem;
  }
  h4,
  p,
  dl,
  dd {
    margin: 0;
  }
  h4 {
    margin-bottom: 0.35rem;
    font-size: 0.79rem;
    overflow-wrap: anywhere;
  }
  dl {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 6.5rem), 1fr));
    gap: 0.25rem 0.6rem;
  }
  small {
    display: block;
    margin-bottom: 0.4rem;
  }
  dt,
  p {
    color: var(--muted);
  }
  dt {
    font-size: 0.7rem;
  }
  dd {
    font: 0.75rem/1.5 var(--mono, monospace);
    overflow-wrap: anywhere;
  }
  p {
    margin-top: 0.35rem;
    line-height: 1.4;
  }
</style>
