import { expect, test } from '@playwright/test';

test('opens the laboratory independently of Python', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(
    'Messaging network laboratory',
  );
  await expect(page.getByRole('status')).toHaveText('Backend disconnected');
});
