import { connect, createSimulation, expect, test } from './backend';

test('keeps runtime controls with the topology and inspection alongside the event timeline', async ({
  page,
  backend,
}) => {
  await page.setViewportSize({ width: 1440, height: 950 });
  await connect(page, backend.url);
  await createSimulation(page, backend);
  const interventions = page
    .locator('.topology-header')
    .getByRole('region', { name: 'Runtime interventions' });
  await expect(
    interventions.getByRole('heading', { name: 'Receiver polling' }),
  ).toBeVisible();
  const pollStatus = page.locator('[data-poll-owner="receiver-1"]');
  const allTransports = page.getByLabel('All transports', { exact: true });
  const [pollBox, runtimeBox, transportsBox] = await Promise.all([
    pollStatus.boundingBox(),
    interventions.boundingBox(),
    allTransports.boundingBox(),
  ]);
  expect(pollBox!.x + pollBox!.width).toBeLessThan(runtimeBox!.x);
  expect(runtimeBox!.x + runtimeBox!.width).toBeLessThan(transportsBox!.x);
  const topology = page.getByRole('group', {
    name: 'Network topology',
    exact: true,
  });
  await topology.locator('[data-node-id="sender-1"]').click();
  const inspector = page.getByRole('complementary', { name: 'Node inspector' });
  await expect(inspector).toBeVisible();
  const availability = interventions.getByRole('group', {
    name: 'Node availability',
  });
  await expect(availability.locator('img')).toHaveAttribute(
    'src',
    '/avatars/sender-1.jpg',
  );
  await availability.getByRole('button', { name: 'Take node offline' }).click();
  await page.mouse.move(0, 0);
  await expect(
    availability.getByRole('button', { name: 'Bring node online' }),
  ).toHaveCSS('background-color', 'rgb(163, 44, 48)');
  await availability.getByRole('button', { name: 'Bring node online' }).click();
  const panel = page.locator('.information');
  await expect(panel).toHaveCSS('background-color', 'rgb(255, 255, 255)');
  const timeline = page.getByRole('region', { name: 'Event timeline' });
  const left = await panel.boundingBox();
  const right = await timeline.boundingBox();
  expect(Math.abs(left!.width - right!.width)).toBeLessThan(2);
  expect(left!.x + left!.width).toBeLessThanOrEqual(right!.x);
  await page.getByRole('button', { name: 'Full screen', exact: true }).click();
  await expect(interventions).toBeHidden();
  await page.keyboard.press('Escape');
  await expect(interventions).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  const stacked = await timeline.boundingBox();
  const narrow = await panel.boundingBox();
  expect(stacked!.y).toBeGreaterThanOrEqual(narrow!.y + narrow!.height);
});
