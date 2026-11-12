import { connect, createSimulation, expect, test } from './backend';

test('inspects a person, hardware node and path from one keyboard-accessible picker', async ({
  page,
  backend,
}) => {
  await connect(page, backend.url);
  const id = await createSimulation(page, backend);
  const topology = (await backend.state(id)).topology;
  const picker = page.getByRole('combobox', { name: 'Inspect node or path' });
  const options = page.getByRole('listbox', { name: 'Nodes and paths' });
  await picker.click();
  const alice = options.getByRole('option', { name: /Alice.*sender-1/i });
  await expect(alice.locator('img')).toHaveAttribute(
    'src',
    '/avatars/sender-1.jpg',
  );
  await alice.click();
  await expect(picker).toHaveValue('Alice');
  await expect(
    page
      .locator('label[for]')
      .filter({ hasText: 'Inspect node or path' })
      .locator('..')
      .locator('.symbol img'),
  ).toHaveAttribute('src', '/avatars/sender-1.jpg');
  await picker.fill('mix-1');
  const firstMix = options.locator('[data-inspect-id="mix-1"]');
  await expect(firstMix.locator('svg')).toBeVisible();
  await picker.press('Enter');
  await expect(picker).toHaveValue(
    topology.nodes.find((n) => n.id === 'mix-1')!.label,
  );
  const path = topology.paths[0];
  await picker.fill(path.id);
  await expect(
    options.locator('[data-inspect-id="' + path.id + '"]'),
  ).toBeVisible();
  await picker.press('Enter');
  await expect(picker).toHaveValue(path.source_id + ' ↔ ' + path.target_id);
  await picker.press('ArrowDown');
  await expect(options).toBeVisible();
  await picker.press('Escape');
  await expect(options).toBeHidden();
  await expect(picker).toBeFocused();
});
