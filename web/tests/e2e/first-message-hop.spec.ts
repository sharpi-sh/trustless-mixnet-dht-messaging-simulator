import { connect, createSimulation, expect, test } from './backend';

test('first-message stepping pauses at a real device departure and becomes available after reset', async ({
  page,
  backend,
  request,
}) => {
  await connect(page, backend.url);
  await page.getByLabel('Random seed', { exact: true }).fill('422');
  const id = await createSimulation(page, backend);
  const seek = page.getByRole('button', {
    name: 'Step to first message hop',
    exact: true,
  });
  await expect(seek).toBeEnabled();
  await expect(
    page.getByText(/Run follows the message from its first hop to Tor/),
  ).toBeVisible();
  await seek.click();
  await expect
    .poll(async () => (await backend.state(id)).status, { timeout: 15000 })
    .toBe('paused');
  const paused = await backend.state(id);
  expect(paused.first_message_hop_sequence).toBeGreaterThan(0);
  const torLeg = paused.topology.paths.find(
    (p) =>
      [p.source_id, p.target_id].includes('sender-1') &&
      [p.source_id, p.target_id].includes('tor-sender-1'),
  );
  expect(Object.keys(torLeg!.active).length).toBeGreaterThan(0);
  const capture = await request.get(
    backend.url + '/api/simulations/' + id + '/events',
    { params: { after: paused.first_message_hop_sequence! - 1, limit: 1 } },
  );
  const departure = (await capture.json()).events[0];
  expect(departure.event_type).toBe('path_transit_started');
  const { sha256, bytes } = departure.payload.cargo;
  expect(sha256).toMatch(/^[a-f0-9]{64}$/);
  expect(bytes).toBeGreaterThan(0);
  const track = page.getByRole('button', {
    name: /msg-1 · sender-1 to tor-sender-1 ·/,
  });
  await expect(track.locator('.message-line')).toHaveCSS(
    'stroke-width',
    '1.25px',
  );
  await expect(track.locator('.message-hit')).toHaveCSS('stroke-width', '13px');
  await track.press('Enter');
  await expect(track.locator('.message-line')).toHaveCSS(
    'stroke-width',
    '2.5px',
  );
  const leg = page.locator(
    '[data-selected-leg="' + departure.payload.transit_id + '"]',
  );
  await expect(leg.getByText(sha256, { exact: true })).toBeVisible();
  await expect(leg.getByText(String(bytes), { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Step', exact: true }).click();
  await expect
    .poll(async () => (await backend.state(id)).sequence)
    .toBeGreaterThan(paused.sequence);
  await expect(leg.getByText(sha256, { exact: true })).toBeVisible();
  await expect(leg.getByText(String(bytes), { exact: true })).toBeVisible();
  await expect(seek).toHaveCount(0);
  await page.getByRole('button', { name: 'Reset', exact: true }).click();
  await expect(seek).toBeEnabled();
});

test('Bob records empty timed polls before Alice sends any packets', async ({
  page,
  backend,
}) => {
  await connect(page, backend.url);
  await page.getByLabel('Random seed', { exact: true }).fill('422');
  await page.getByText('Advanced settings', { exact: true }).click();
  await page.getByLabel('Polling interval (ms)', { exact: true }).fill('1000');
  const id = await createSimulation(page, backend);
  const status = page.locator('[data-poll-owner="receiver-1"]');
  await expect(status).toContainText('Poll every 1000 ms');
  await page
    .getByRole('button', { name: 'Step to first message hop', exact: true })
    .click();
  await expect(status).toContainText(/Last request \d+ ms · Empty at \d+ ms/);
  await expect
    .poll(async () => (await backend.state(id)).status)
    .toBe('paused');
  const snapshot = await backend.state(id);
  const emptyAt = Number(
    (await status.innerText()).match(/Empty at (\d+) ms/)![1],
  );
  expect(emptyAt).toBeLessThanOrEqual(snapshot.simulation_time_ms);
  expect(
    snapshot.devices
      .find((d) => d.id === 'receiver-1')
      ?.logs.filter((l) => l.state === 'received'),
  ).toEqual([]);
});
