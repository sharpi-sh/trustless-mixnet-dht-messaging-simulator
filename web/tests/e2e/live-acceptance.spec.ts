import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import type { Page, Locator } from '@playwright/test';
import type { LabEvent, Snapshot } from '../../src/lib/types';
import { connect, createSimulation, expect, test } from './backend';

const edited = 'Bob, meet me at the east pier.';
async function configure(page: Page) {
  const field = (name: string) => page.getByLabel(name, { exact: true });
  for (const [name, value] of Object.entries({
    Senders: 3,
    'Exchanges per conversation': 5,
    'Random seed': 254,
  })) {
    await field(name).fill(String(value));
  }
  await field('Enable receiver polling').uncheck();
  await page
    .getByRole('combobox', { name: /^Node availability/ })
    .selectOption('scheduled');
  for (const [i, [uid, start, duration]] of [
    ['mix-5', 5, 500],
    ['mix-15', 8, 500000],
  ].entries()) {
    await page.getByRole('button', { name: 'Add outage', exact: true }).click();
    await field('Node ID').nth(i).fill(String(uid));
    await field('Start (ms)').nth(i).fill(String(start));
    await field('Duration (ms)').nth(i).fill(String(duration));
  }
  await page.getByText('Advanced settings', { exact: true }).click();
  for (const [name, value] of Object.entries({
    'Polling interval (ms)': 600,
    'Cells per response': 6,
    'Payloads per minute': 90,
    'Client loops per minute': 0.15,
    'Drop packets per minute': 0.15,
    'Mix loops per minute': 0.15,
    'Path transit delay (ms)': 8,
    'Maximum jitter (ms)': 4,
    'Mix delay rate (per second)': 45,
    'DHT nodes': 5,
    'Storage nodes': 5,
    'Maximum retries': 10,
    'Acknowledgement timeout (ms)': 30,
  }))
    await field(name).fill(String(value));
}

async function changePace(slider: Locator, ms: number) {
  // Browser range controls have no Playwright fill action. Use the same change
  // event a pointer release produces; the normal WebSocket handler owns pacing.
  await slider.evaluate((element, value) => {
    const input = element as HTMLInputElement;
    input.value = String(value);
    input.dispatchEvent(new Event('change', { bubbles: true }));
  }, ms);
}

async function chooseFilter(input: Locator, value: string) {
  if ((await input.evaluate((el) => el.tagName)) === 'SELECT')
    await input.selectOption(value);
  else await input.fill(value);
}

function assertDelivery(state: Snapshot, initial: Snapshot) {
  const expected = new Map(initial.messages.map((m) => [m.id, m]));
  const receipts: string[] = [];
  for (const person of state.devices) {
    const received = person.logs.filter((log) => log.state === 'received');
    expect(received.length).toBe(person.role === 'receiver' ? 15 : 5);
    for (const entry of received) {
      const message = expected.get(entry.message_id)!;
      expect(person.id).toBe(message.target_id);
      expect(entry.direction).toBe(message.direction);
      const signer = state.devices.find((d) => d.id === message.sender_id)!;
      expect(signer.signing_fingerprint).toMatch(/^[a-f0-9]{64}$/);
      expect(entry.verified_signer_id).toBe(signer.id);
      expect(entry.signing_fingerprint).toBe(signer.signing_fingerprint);
      expect(entry.text).toBe(message.id === 'msg-1' ? edited : message.text);
      receipts.push(entry.message_id);
    }
  }
  expect(receipts.sort()).toEqual([...expected.keys()].sort());
}

test('completes the live thirty-transmission scenario with edited text, polling, blocked routing and recovery', async ({
  page,
  backend,
}) => {
  test.setTimeout(240000);
  page.setDefaultTimeout(15000);
  await page.setViewportSize({ width: 1500, height: 1000 });
  const errors: string[] = [];
  page.on('pageerror', (err) => errors.push(err.message));
  const events = new Map<number, LabEvent>();
  page.on('websocket', (socket) => {
    if (!socket.url().endsWith('/ws')) return;
    socket.on('framereceived', ({ payload }) => {
      const frame = JSON.parse(String(payload));
      for (const event of (frame.delta?.events ??
        frame.events ??
        []) as LabEvent[])
        events.set(event.sequence, event);
    });
  });
  const recorded = (type: string) =>
    [...events.values()].filter((e) => e.event_type === type);
  await connect(page, backend.url);
  await configure(page);
  const id = await createSimulation(page, backend);
  const read = () => backend.state(id);
  const initial = await read();
  expect(initial).toMatchObject({
    status: 'ready',
    step_delay_ms: 500,
    random_seed: 254,
  });
  expect(initial.topology.nodes.filter((n) => n.kind === 'mix')).toHaveLength(
    15,
  );
  expect(initial.messages).toHaveLength(30);
  const button = (name: string) =>
    page.getByRole('button', { name, exact: true });
  const field = (name: string) => page.getByLabel(name, { exact: true });
  await field('Message text msg-1').fill(edited);
  await button('Save messages').click();
  await expect
    .poll(
      async () => (await read()).messages.find((m) => m.id === 'msg-1')?.text,
    )
    .toBe(edited);
  const path = initial.topology.paths.find(
    (p) => p.source_id === 'sender-1' && p.target_id === 'tor-sender-1',
  )!;
  await page
    .getByRole('combobox', { name: /^Inspect path/ })
    .selectOption(path.id);
  await button('Block path').click();
  const graph = page.getByRole('group', {
    name: 'Network topology',
    exact: true,
  });
  await expect(
    graph.locator('[data-path-id="' + path.id + '"]'),
  ).toHaveAttribute('data-path-state', 'blocked');
  await button('Run').click();
  const slider = page.getByRole('slider', { name: /Playback delay/i });
  await changePace(slider, 12);
  await expect.poll(async () => (await read()).step_delay_ms).toBe(12);
  await expect
    .poll(
      () =>
        recorded('path_transit_failed').some(
          (e) =>
            e.message_id === 'msg-1' &&
            e.payload.path_id === path.id &&
            e.payload.reason === 'blocked',
        ),
      { timeout: 45000, intervals: [80, 150] },
    )
    .toBe(true);
  await button('Restore path').click();
  await expect
    .poll(
      async () =>
        (await read()).topology.paths.find((p) => p.id === path.id)?.blocked,
    )
    .toBe(false);

  await expect(graph.locator('[data-transit-id]').first()).toBeAttached({
    timeout: 15000,
  });
  await button('Pause').click();
  await expect.poll(async () => (await read()).status).toBe('paused');
  let paused = await read();
  const activeTransit = (state: Snapshot) =>
    state.topology.paths.flatMap((p) => Object.keys(p.active))[0];
  for (let i = 0; i < 80 && !activeTransit(paused); i++) {
    const sequence = paused.sequence;
    await button('Step').click();
    await expect
      .poll(async () => (await read()).sequence)
      .toBeGreaterThan(sequence);
    paused = await read();
  }
  const transitId = activeTransit(paused);
  expect(transitId).toBeTruthy();
  const marker = graph.locator('[data-transit-id="' + transitId + '"]');
  await expect(marker).toBeAttached();
  const point = await marker.getAttribute('transform');
  await page.evaluate(
    () =>
      new Promise((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(resolve)),
      ),
  );
  expect(await marker.getAttribute('transform')).toBe(point);
  expect((await read()).simulation_time_ms).toBe(paused.simulation_time_ms);

  await changePace(slider, 1);
  await expect.poll(async () => (await read()).step_delay_ms).toBe(1);
  await button('Resume').click();
  await expect
    .poll(() => recorded('manifest_published').length, { timeout: 30000 })
    .toBeGreaterThan(0);
  const stored = recorded('manifest_published')[0].simulation_time_ms;
  await expect
    .poll(async () => (await read()).simulation_time_ms, { timeout: 15000 })
    .toBeGreaterThanOrEqual(stored + 600);
  const waiting = await read();
  expect(
    waiting.devices.find((p) => p.id === 'receiver-1')?.polling_enabled,
  ).toBe(false);
  expect(
    waiting.devices
      .flatMap((p) => p.logs)
      .filter((l) => l.state === 'received'),
  ).toHaveLength(0);
  await button('Enable all receiver polling').click();
  await expect
    .poll(
      async () =>
        (await read()).devices.find((p) => p.id === 'receiver-1')
          ?.polling_enabled,
    )
    .toBe(true);
  await expect(
    graph.locator('[data-transit-id][data-lane="reply"]').first(),
  ).toBeAttached({ timeout: 45000 });
  await expect
    .poll(async () => (await read()).status, {
      timeout: 155000,
      intervals: [250, 500, 1000],
    })
    .toBe('completed');
  await expect(
    page.getByText('completed', { exact: true }).first(),
  ).toBeVisible({ timeout: 30000 });
  const final = await read();
  assertDelivery(final, initial);
  expect(final.topology.nodes.find((n) => n.id === 'mix-5')?.history).toEqual([
    [5, false],
    [505, true],
  ]);
  expect(
    final.topology.nodes.find((n) => n.id === 'mix-15')?.history[0],
  ).toEqual([8, false]);
  const failure = recorded('path_transit_failed').find(
    (e) =>
      e.message_id === 'msg-1' &&
      e.payload.path_id === path.id &&
      e.payload.reason === 'blocked',
  )!;
  const retry = recorded('packet_retry_scheduled').find(
    (e) => e.payload.previous_packet_id === failure.payload.token,
  )!;
  const route = (packet: unknown) =>
    recorded('mixnet_route_constructed').find(
      (e) => e.payload.packet_id === packet,
    )!;
  expect(route(retry.payload.packet_id).payload.decision_seed).not.toBe(
    route(failure.payload.token).payload.decision_seed,
  );
  expect(
    recorded('path_transit_failed').some(
      (e) => e.message_id && e.payload.reason === 'unresponsive',
    ),
  ).toBe(true);
  expect(recorded('simulation_error')).toEqual([]);
  const lineage = final.lineage
    .filter((row) => row.message_id === 'msg-1')
    .map((r) => r.operation);
  for (const op of [
    'message_signed',
    'sender_signature_verified',
    'reply_key_encapsulated',
    'fragment_stored',
    'manifest_published',
    'fragment_retrieved',
    'message_decrypted',
    'reply_key_learned',
  ])
    expect(lineage).toContain(op);
  expect(lineage.indexOf('reply_key_learned')).toBeGreaterThan(
    lineage.indexOf('sender_signature_verified'),
  );

  await page
    .getByRole('combobox', { name: /^Inspect node/ })
    .selectOption('receiver-1');
  const inspector = page.getByRole('complementary', {
    name: 'Node inspector',
    exact: true,
  });
  await expect(
    inspector.getByRole('heading', { name: 'Device log' }),
  ).toBeVisible();
  await expect(inspector.getByText(edited, { exact: true })).toBeVisible();
  const alice = final.devices.find((d) => d.id === 'sender-1')!;
  const bob = final.devices.find((d) => d.id === 'receiver-1')!;
  await expect(
    inspector.getByText(bob.signing_fingerprint!, { exact: true }),
  ).toBeVisible();
  const receipt = inspector
    .getByRole('listitem')
    .filter({ has: page.getByText('received · msg-1', { exact: true }) });
  await receipt.getByText('Signature verified', { exact: true }).click();
  await expect(receipt.getByText(alice.id, { exact: true })).toBeVisible();
  await expect(
    receipt.getByText(alice.signing_fingerprint!, { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'Event timeline', exact: true }),
  ).toBeVisible();
  await chooseFilter(
    page.getByRole('combobox', { name: /^Timeline message/ }),
    'msg-1',
  );
  await chooseFilter(
    page.getByRole('combobox', { name: /^Event category/ }),
    'Failures/retries',
  );
  const timeline = page.getByRole('region', {
    name: 'Event timeline',
    exact: true,
  });
  await timeline
    .getByRole('button', { name: 'packet_retry_scheduled', exact: true })
    .first()
    .click();
  await expect(
    timeline.getByRole('heading', {
      name: 'packet_retry_scheduled',
      exact: true,
    }),
  ).toBeVisible();
  await expect(timeline.locator('pre')).toContainText('"previous_packet_id"');
  await expect(timeline.locator('tbody tr td:nth-child(5)').first()).toHaveText(
    'msg-1',
  );
  await expect(
    page.getByRole('heading', { name: 'Cryptographic lineage', exact: true }),
  ).toBeVisible();
  await chooseFilter(
    page.getByRole('combobox', { name: /^Lineage message/ }),
    'msg-1',
  );
  const ledger = page.getByRole('region', {
    name: 'Cryptographic lineage',
    exact: true,
  });
  await expect(
    ledger.getByText('reply_key_encapsulated', { exact: true }),
  ).toBeVisible();
  await expect(
    ledger.getByText('reply_key_learned', { exact: true }),
  ).toBeVisible();
  await expect(
    ledger.getByText('fragment_retrieved', { exact: true }).first(),
  ).toBeVisible();
  await expect(
    ledger.getByText('message_decrypted', { exact: true }),
  ).toBeVisible();
  for (const operation of ['message_signed', 'sender_signature_verified']) {
    await expect(ledger.getByText(operation, { exact: true })).toBeVisible();
  }
  for (const role of ['sender', 'receiver'] as const) {
    const device = final.devices.find((p) => p.role === role)!;
    const panel = page.getByRole('complementary', {
      name:
        role === 'sender' ? 'Sender conversations' : 'Recipient conversations',
      exact: true,
    });
    const messages = panel.getByRole('list', {
      name: device.label + ' chat messages',
    });
    const sentReceived = device.logs.filter((row) =>
      ['sent', 'replied', 'received'].includes(row.state),
    );
    const rows = messages.locator('li');
    expect(
      await rows.evaluateAll((items) =>
        items.map((row) => [
          row.getAttribute('data-message-id'),
          row.getAttribute('data-side'),
          row.querySelector('p')?.textContent,
          row.querySelector('time')?.getAttribute('title'),
        ]),
      ),
    ).toEqual(
      sentReceived.map((row) => [
        row.message_id,
        row.state === 'received' ? 'incoming' : 'outgoing',
        row.text,
        row.simulation_time_ms + ' ms',
      ]),
    );
    const incoming = sentReceived.filter((row) => row.state === 'received');
    await expect(
      messages.getByText('Signature verified', { exact: true }),
    ).toHaveCount(incoming.length);
    const first = incoming[0];
    const bubble = messages.locator(
      '[data-message-id="' + first.message_id + '"]',
    );
    await bubble.getByText('Signature verified', { exact: true }).click();
    await expect(
      bubble.getByText(first.verified_signer_id!, { exact: true }),
    ).toBeVisible();
    await expect(
      bubble.getByText(first.signing_fingerprint!, { exact: true }),
    ).toBeVisible();
    await bubble.getByText('Signature verified', { exact: true }).click();
    const card = graph.locator('[data-node-id="' + device.id + '"]');
    await expect(card).not.toContainText(edited);
    await expect(card.locator('[data-last-sent]')).toHaveAttribute(
      'data-last-sent',
      String(
        sentReceived.filter((row) => row.state !== 'received').at(-1)!
          .simulation_time_ms,
      ),
    );
    await expect(card.locator('[data-last-received]')).toHaveAttribute(
      'data-last-received',
      String(
        sentReceived.filter((row) => row.state === 'received').at(-1)!
          .simulation_time_ms,
      ),
    );
  }
  const recipient = page.getByRole('complementary', {
    name: 'Recipient conversations',
    exact: true,
  });
  await recipient
    .getByRole('combobox', { name: 'Recipient thread' })
    .selectOption('conv-2');
  await expect(recipient.locator('li')).toHaveCount(10);
  await recipient
    .getByRole('combobox', { name: 'Recipient thread' })
    .selectOption('');
  expect(errors).toEqual([]);
  if (process.env.SIM_GRAPH_EVIDENCE) {
    await mkdir(process.env.SIM_GRAPH_EVIDENCE, { recursive: true });
    await graph.scrollIntoViewIfNeeded();
    await page.screenshot({
      path: join(process.env.SIM_GRAPH_EVIDENCE, 'acceptance.png'),
      animations: 'disabled',
    });
  }
});

test('applies selected-receiver, node and stage-boundary interventions to Python', async ({
  page,
  backend,
}) => {
  await connect(page, backend.url);
  await page.getByLabel('Receivers', { exact: true }).fill('2');
  const id = await createSimulation(page, backend),
    read = () => backend.state(id);
  const before = await read(),
    panel = page.getByRole('region', {
      name: 'Runtime interventions',
      exact: true,
    });
  const button = (name: string) =>
    panel.getByRole('button', { name, exact: true });
  const inspect = page.getByRole('combobox', { name: /^Inspect node/ });
  await inspect.selectOption('receiver-2');
  await button('Disable receiver polling').click();
  const polling = async () =>
    (await read()).devices
      .filter((d) => d.role === 'receiver')
      .map((d) => d.polling_enabled);
  await expect.poll(polling).toEqual([true, false]);
  await expect(panel.getByRole('status')).toContainText('Applied');
  await button('Enable receiver polling').click();
  await expect.poll(polling).toEqual([true, true]);
  await inspect.selectOption('mix-1');
  await button('Take node offline').click();
  await expect
    .poll(
      async () =>
        (await read()).topology.nodes.find((n) => n.id === 'mix-1')?.online,
    )
    .toBe(false);
  await button('Bring node online').click();
  await expect
    .poll(
      async () =>
        (await read()).topology.nodes.find((n) => n.id === 'mix-1')?.online,
    )
    .toBe(true);
  const boundary = before.topology.paths.find(
    (p) => p.source_id === 'provider-west' && p.target_id.startsWith('mix-'),
  )!.boundary;
  const expected = before.topology.paths
    .filter((p) => p.boundary === boundary)
    .map((p) => p.id)
    .sort();
  expect(expected.length).toBeGreaterThan(1);
  await panel
    .getByRole('combobox', { name: /^Stage boundary/ })
    .selectOption(boundary);
  await panel
    .getByRole('checkbox', { name: 'Drop traffic already in flight' })
    .check();
  await button('Block boundary').click();
  const blocked = async () =>
    (await read()).topology.paths
      .filter((p) => p.blocked)
      .map((p) => p.id)
      .sort();
  await expect.poll(blocked).toEqual(expected);
  await button('Restore boundary').click();
  await expect.poll(blocked).toEqual([]);
  await expect(panel.getByRole('status')).toContainText('Applied');
});
