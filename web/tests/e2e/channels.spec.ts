import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import type { Locator } from '@playwright/test';
import { connect, createSimulation, expect, test } from './backend';
import type { IPHop } from '../../src/lib/types';

async function assertAddresses(
  region: Locator,
  hop: IPHop,
  received: boolean,
  proxyEgress?: string | null,
) {
  for (const [label, value] of [
    ['Source IP', hop.source_ip],
    ['Destination IP', hop.destination_ip],
    [
      received ? 'Observed source IP' : 'Projected source IP',
      hop.observed_source_ip,
    ],
    [received ? 'Observer' : 'Receiving endpoint', hop.observer],
  ]) {
    const field = region
      .locator('dl > div')
      .filter({ has: region.page().getByText(label, { exact: true }) });
    await expect(field.locator('dd')).toHaveText(value);
  }
  await expect(region).toContainText(hop.description);
  if (proxyEgress) {
    const field = region.locator('dl > div').filter({
      has: region.page().getByText('Proxy egress IP', { exact: true }),
    });
    await expect(field.locator('dd')).toHaveText(proxyEgress);
  }
  await expect(
    region.getByText(received ? 'Received by peer' : 'Configured projection', {
      exact: true,
    }),
  ).toBeVisible();
}

test('shows Alice’s IP at Shadowsocks, the proxy IP at the provider and Bob’s direct IP', async ({
  page,
  backend,
}) => {
  test.setTimeout(90_000);
  await page.setViewportSize({ width: 1500, height: 960 });
  await connect(page, backend.url);
  const sender = page.getByRole('combobox', {
    name: 'Alice channel',
    exact: true,
  });
  const recipient = page.getByRole('combobox', {
    name: 'Bob channel',
    exact: true,
  });
  await expect(sender).toHaveValue('tor');
  await expect(recipient).toHaveValue('tor');
  await sender.selectOption('shadowsocks');
  await recipient.selectOption('direct');
  await page.getByLabel('Random seed', { exact: true }).fill('422');
  await page.getByLabel('Playback delay (ms)', { exact: true }).fill('0');
  const id = await createSimulation(page, backend);
  const initial = await backend.state(id);
  expect(initial.config).toMatchObject({
    participant_channels: { 'sender-1': 'shadowsocks', 'receiver-1': 'direct' },
  });
  const node = (id: string) => initial.topology.nodes.find((n) => n.id === id)!;
  const alice = node('sender-1'),
    bob = node('receiver-1');
  const proxy = initial.topology.nodes.find((n) => n.kind === 'shadowsocks')!;
  const direct = initial.topology.nodes.find((n) => n.kind === 'direct')!;
  const west = node('provider-west'),
    east = node('provider-east');
  expect(direct.simulated_address).toBe(bob.simulated_address);
  expect(proxy.egress_address).toBeTruthy();
  expect(proxy.egress_address).not.toBe(alice.simulated_address);
  const graph = page.getByRole('group', {
    name: 'Network topology',
    exact: true,
  });
  for (const device of [alice, bob])
    await expect(
      page
        .getByRole('complementary', {
          name:
            device.id === alice.id
              ? 'Sender conversations'
              : 'Recipient conversations',
          exact: true,
        })
        .locator('[data-device-ip]'),
    ).toHaveText(device.simulated_address);
  await expect(
    page.getByText(
      /Run follows the message from its first hop to Outline Shadowsocks/,
    ),
  ).toBeVisible();
  await expect(page.locator('main > footer')).toContainText(
    'Outline Shadowsocks / Direct connection',
  );
  const path = (a: string, b: string) =>
    initial.topology.paths.find(
      (p) =>
        (p.source_id === a && p.target_id === b) ||
        (p.source_id === b && p.target_id === a),
    )!;
  const toProxy = path(alice.id, proxy.id),
    onward = path(proxy.id, west.id),
    fromBob = path(direct.id, east.id);
  expect(toProxy.ip_hops![alice.id].observed_source_ip).toBe(
    alice.simulated_address,
  );
  expect(onward.ip_hops![proxy.id].observed_source_ip).toBe(
    proxy.egress_address,
  );
  expect(fromBob.ip_hops![direct.id].observed_source_ip).toBe(
    bob.simulated_address,
  );
  for (const p of [toProxy, onward, fromBob]) {
    await graph.locator('[data-path-id="' + p.id + '"]').press('Enter');
    const configured = page.getByRole('complementary', {
      name: 'Path inspector',
      exact: true,
    });
    for (const [source, hop] of Object.entries(p.ip_hops!)) {
      await assertAddresses(
        configured.getByRole('region', {
          name: source + ' → ' + hop.observer,
          exact: true,
        }),
        hop,
        false,
        p === toProxy || p === onward ? proxy.egress_address : null,
      );
    }
  }
  await page.getByRole('button', { name: 'Run', exact: true }).click();
  await expect
    .poll(async () => (await backend.state(id)).status, { timeout: 60_000 })
    .toBe('completed');
  const final = await backend.state(id);
  for (const d of final.devices) {
    const messages = d.logs.filter((row) => row.state === 'received');
    expect(messages).toHaveLength(1);
    expect(messages[0].verified_signer_id).toBe(
      d.id === alice.id ? bob.id : alice.id,
    );
  }
  for (const [source, target, p] of [
    [alice, proxy, toProxy],
    [proxy, west, onward],
    [direct, east, fromBob],
  ] as const) {
    const messageId = source.id === direct.id ? 'msg-2' : 'msg-1';
    const retained = graph.locator(
      '[data-message-path][data-message-id="' +
        messageId +
        '"][data-source="' +
        source.id +
        '"][data-target="' +
        target.id +
        '"]',
    );
    await retained.press('Enter');
    const selectedJourney = graph.locator(
      '[data-message-id="' + messageId + '"][data-journey-selected="true"]',
    );
    await expect(selectedJourney.first()).toHaveCSS('opacity', '1');
    const otherMessageId = messageId === 'msg-1' ? 'msg-2' : 'msg-1';
    const mutedJourney = graph.locator(
      '[data-message-id="' + otherMessageId + '"][data-journey-muted="true"]',
    );
    await expect(mutedJourney.first()).toHaveCSS('opacity', '0.1');
    const record = page.getByRole('region', {
      name: 'Recorded IP visibility',
      exact: true,
    });
    await assertAddresses(
      record,
      p.ip_hops![source.id],
      true,
      p === toProxy || p === onward ? proxy.egress_address : null,
    );
    const directory = process.env.SIM_GRAPH_EVIDENCE;
    if (directory) {
      await mkdir(directory, { recursive: true });
      await page
        .getByRole('region', { name: 'Recorded message transit', exact: true })
        .screenshot({
          path: join(
            directory,
            'ip-' + source.id + '-to-' + target.id + '.png',
          ),
        });
    }
  }
});

test('assigns three different channels to three senders in the same simulation', async ({
  page,
  backend,
}) => {
  await connect(page, backend.url);
  const addSender = page.getByRole('button', {
    name: 'Add another sender',
    exact: true,
  });
  await addSender.click();
  await addSender.click();
  await page
    .getByLabel('Carol channel', { exact: true })
    .selectOption('shadowsocks');
  await page
    .getByLabel('David channel', { exact: true })
    .selectOption('direct');
  await expect(page.getByLabel('Alice channel', { exact: true })).toHaveValue(
    'tor',
  );
  const id = await createSimulation(page, backend);
  const state = await backend.state(id);
  for (const [owner, channel] of [
    ['sender-1', 'tor'],
    ['sender-2', 'shadowsocks'],
    ['sender-3', 'direct'],
    ['receiver-1', 'tor'],
  ]) {
    const endpoint = `${channel}-${owner}`;
    expect(
      state.devices.find((device) => device.id === owner)?.channel_id,
    ).toBe(endpoint);
    expect(
      state.topology.paths.some(
        (path) =>
          [path.source_id, path.target_id].includes(owner) &&
          [path.source_id, path.target_id].includes(endpoint),
      ),
    ).toBe(true);
  }
});

test('adds and removes participant rows independently and enforces both roster limits', async ({
  page,
  backend,
}) => {
  await connect(page, backend.url);
  await expect(
    page.getByRole('spinbutton', { name: /^(Senders|Receivers)$/ }),
  ).toHaveCount(0);
  const channel = (name: string) =>
    page.getByLabel(name + ' channel', { exact: true });
  const remove = (name: string) =>
    page.getByRole('button', { name: 'Remove ' + name, exact: true });
  const add = (role: string) =>
    page.getByRole('button', { name: 'Add another ' + role, exact: true });
  await channel('Alice').selectOption('direct');
  await add('sender').click();
  await channel('Carol').selectOption('shadowsocks');
  await add('recipient').click();
  await channel('Lena').selectOption('shadowsocks');
  await remove('Carol').click();
  await expect(channel('Carol')).toHaveCount(0);
  await expect(channel('Lena')).toHaveValue('shadowsocks');
  await add('sender').click();
  await expect(channel('Carol')).toHaveValue('tor');
  await expect(channel('Alice')).toHaveValue('direct');
  for (const role of ['sender', 'recipient']) {
    for (let count = 2; count < 10; count++) await add(role).click();
    await expect(add(role)).toBeDisabled();
  }
  await expect(channel('Kai')).toBeVisible();
  await expect(channel('Tess')).toBeVisible();
  await remove('Tess').click();
  await expect(add('recipient')).toBeEnabled();
  await expect(add('sender')).toBeDisabled();
});
