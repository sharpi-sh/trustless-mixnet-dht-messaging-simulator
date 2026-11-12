import { connect, createSimulation, expect, test } from './backend';

test('first-message stepping pauses at a real device departure and becomes available after reset', async ({
  page,
  backend,
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
    page.getByText(/Bootstrap and cover traffic can precede/),
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
  await expect(seek).toHaveCount(0);
  await page.getByRole('button', { name: 'Reset', exact: true }).click();
  await expect(seek).toBeEnabled();
});
