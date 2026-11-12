<script lang="ts">
  import { verifiedSigner } from './conversation';
  import type { DeviceLog } from './types';

  let { row }: { row: DeviceLog } = $props();
  const signer = $derived(verifiedSigner(row));
</script>

{#if signer}
  <details class="receipt">
    <summary>Signature verified</summary>
    <dl>
      <dt>Verified signer</dt>
      <dd>{signer}</dd>
      <dt>Signing key fingerprint</dt>
      <dd><code>{row.signing_fingerprint}</code></dd>
    </dl>
  </details>
{:else if row.state === 'received'}
  <small class="unverified">No signature evidence recorded</small>
{/if}

<style>
  .receipt,
  .unverified {
    display: block;
    margin-top: 4px;
    font-size: 0.65rem;
    line-height: 1.4;
  }
  summary {
    width: fit-content;
    cursor: pointer;
    color: #315b44;
    font-weight: 600;
  }
  dl {
    margin: 5px 0 0;
  }
  dt,
  .unverified {
    color: #59675c;
  }
  dd {
    margin: 0 0 3px;
    overflow-wrap: anywhere;
  }
  code {
    font-size: inherit;
  }
</style>
