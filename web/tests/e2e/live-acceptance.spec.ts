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
  await field('Node availability').selectOption('scheduled');
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
  await field('Inspect path').selectOption(path.id);
  await button('Run').click();
  await button('Block path').click();
  const graph = page.getByRole('group', {
    name: 'Network topology',
    exact: true,
  });
  await expect(
    graph.locator('[data-path-id="' + path.id + '"]'),
  ).toHaveAttribute('data-path-state', 'blocked');
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
  for (
    let i = 0;
    i < 80 && !(await graph.locator('[data-transit-id]').count());
    i++
  ) {
    const sequence = (await read()).sequence;
    await button('Step').click();
    await expect
      .poll(async () => (await read()).sequence)
      .toBeGreaterThan(sequence);
  }
  const marker = graph.locator('[data-transit-id]').first();
  await expect(marker).toBeAttached();
  const paused = await read();
  const transitId = await marker.getAttribute('data-transit-id');
  const point = await marker.getAttribute('transform');
  expect(
    paused.topology.paths.some((p) => Object.hasOwn(p.active, transitId!)),
  ).toBe(true);
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
    'reply_key_encapsulated',
    'fragment_stored',
    'manifest_published',
    'fragment_retrieved',
    'message_decrypted',
    'reply_key_learned',
  ])
    expect(lineage).toContain(op);
  expect(lineage.indexOf('reply_key_learned')).toBeGreaterThan(
    lineage.indexOf('message_decrypted'),
  );

  await field('Inspect node').selectOption('receiver-1');
  const inspector = page.getByRole('complementary', {
    name: 'Node inspector',
    exact: true,
  });
  await expect(
    inspector.getByRole('heading', { name: 'Device log' }),
  ).toBeVisible();
  await expect(inspector.getByText(edited, { exact: true })).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'Event timeline', exact: true }),
  ).toBeVisible();
  await chooseFilter(field('Timeline message'), 'msg-1');
  await expect(
    page.getByRole('heading', { name: 'Cryptographic lineage', exact: true }),
  ).toBeVisible();
  await chooseFilter(field('Lineage message'), 'msg-1');
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
