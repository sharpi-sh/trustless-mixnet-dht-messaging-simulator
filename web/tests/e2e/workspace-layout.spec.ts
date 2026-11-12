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
  const topology = page.getByRole('group', {
    name: 'Network topology',
    exact: true,
  });
  await topology.locator('[data-node-id="sender-1"]').click();
  const inspector = page.getByRole('complementary', { name: 'Node inspector' });
  await expect(inspector).toBeVisible();
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
