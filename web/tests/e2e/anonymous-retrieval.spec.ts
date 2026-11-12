import { connect, createSimulation, expect, test } from './backend';

test('shows mixed manifest and fragment exchanges during a signed round trip', async ({
  page,
  backend,
}) => {
  test.setTimeout(90_000);
  await connect(page, backend.url);
  await page.getByLabel('Random seed', { exact: true }).fill('29');
  await page.getByLabel('Playback delay (ms)', { exact: true }).fill('0');
  const id = await createSimulation(page, backend);
  const initial = await backend.state(id);
  const nodes = new Map(
    initial.topology.nodes.map((node) => [node.id, node.kind]),
  );
  for (const path of initial.topology.paths) {
    const kinds = [nodes.get(path.source_id), nodes.get(path.target_id)];
    expect(
      kinds.includes('tor') &&
        (kinds.includes('dht') || kinds.includes('storage')),
    ).toBe(false);
  }
  await page.getByRole('button', { name: 'Run', exact: true }).click();
  await expect
    .poll(async () => (await backend.state(id)).status, { timeout: 65_000 })
    .toBe('completed');
  const final = await backend.state(id);
  expect(Object.values(final.outcomes)).toEqual(['received', 'received']);
  await page
    .getByLabel('Event category', { exact: true })
    .selectOption('Anonymous retrieval');
  for (const operation of ['fragment', 'manifest']) {
    await page.getByLabel('Search events', { exact: true }).fill(operation);
    await expect(
      page
        .getByRole('button', { name: 'retrieval_reply_received', exact: true })
        .last(),
    ).toBeVisible();
  }
});
