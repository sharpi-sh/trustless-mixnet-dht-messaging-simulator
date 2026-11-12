import { connect, expect, test } from './backend';

test('shows roster portraits and divides setup into equal desktop columns that stack on mobile', async ({
  page,
  backend,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await connect(page, backend.url);
  const network = page.getByRole('region', { name: 'Network setup' });
  const conversations = page.getByRole('heading', {
    name: 'Conversations',
    exact: true,
  });
  await network.getByRole('button', { name: 'Add another sender' }).click();
  for (const id of ['sender-1', 'sender-2', 'receiver-1']) {
    const img = network.locator(`img[src="/avatars/${id}.jpg"]`);
    await expect(img).toBeVisible();
    expect(
      await img.evaluate(async (element: HTMLImageElement) => {
        await element.decode();
        return element.naturalWidth;
      }),
    ).toBeGreaterThan(0);
  }
  const desktop = await network.boundingBox();
  const right = await conversations.boundingBox();
  expect(right!.x).toBeGreaterThan(desktop!.x + desktop!.width);
  expect(right!.width).toBeCloseTo(desktop!.width, 0);
  expect(right!.y).toBeCloseTo(desktop!.y, 0);
  expect(
    (await page.getByRole('heading', { name: 'Run settings' }).boundingBox())!
      .x,
  ).toBe(right!.x);

  await page.setViewportSize({ width: 375, height: 812 });
  const mobile = await network.boundingBox();
  const below = await conversations.boundingBox();
  expect(below!.x).toBe(mobile!.x);
  expect(below!.y).toBeGreaterThanOrEqual(mobile!.y + mobile!.height);
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(375);
});
