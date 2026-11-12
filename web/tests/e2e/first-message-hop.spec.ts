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
  await track.press('Enter');
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
