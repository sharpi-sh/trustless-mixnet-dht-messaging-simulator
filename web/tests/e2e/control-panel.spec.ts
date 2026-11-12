import type { WebSocketRoute } from '@playwright/test';
import { connect, createSimulation, expect, test } from './backend';

test('displays an unavailable Python endpoint without enabling simulation creation', async ({
  page,
}) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(
    'Messaging network laboratory',
  );
  await page
    .getByLabel('Backend endpoint', { exact: true })
    .fill('http://127.0.0.1:1');
  await page
    .getByRole('button', { name: 'Test connection', exact: true })
    .click();
  await expect(page.getByRole('alert')).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Create simulation', exact: true }),
  ).not.toBeVisible();
});

test('creates, edits and controls a real simulation', async ({
  page,
  backend,
}) => {
  await connect(page, backend.url);
  await page.getByLabel('Random seed', { exact: true }).fill('712345');
  const id = await createSimulation(page, backend);
  const read = () => backend.state(id);
  expect((await read()).random_seed).toBe(712345);
  const message = page.getByLabel('Message text msg-1', { exact: true });
  const edited = 'Bring the printed map to the harbour.';
  await message.fill(edited);
  await page
    .getByRole('button', { name: 'Save messages', exact: true })
    .click();
  await expect
    .poll(
      async () => (await read()).messages.find((m) => m.id === 'msg-1')?.text,
    )
    .toBe(edited);
  const button = (name: string) =>
    page.getByRole('button', { name, exact: true });
  await button('Run').click();
  await expect.poll(async () => (await read()).status).toBe('running');
  await expect(page.getByText('running', { exact: true })).toBeVisible();
  await button('Pause').click();
  await expect.poll(async () => (await read()).status).toBe('paused');
  await expect(page.getByText('paused', { exact: true })).toBeVisible();
  const beforeStep = (await read()).sequence;
  await button('Step').click();
  await expect
    .poll(async () => (await read()).sequence)
    .toBeGreaterThan(beforeStep);
  expect((await read()).status).toBe('paused');
  await expect(page.getByText('paused', { exact: true })).toBeVisible();
  await button('Resume').click();
  await expect.poll(async () => (await read()).status).toBe('running');
  await expect(page.getByText('running', { exact: true })).toBeVisible();
  await button('Stop').click();
  await expect.poll(async () => (await read()).status).toBe('stopped');
  await expect(page.getByText('stopped', { exact: true })).toBeVisible();
  await button('Reset').click();
  await expect.poll(async () => (await read()).epoch).toBe(1);
  const reset = await read();
  expect(reset.status).toBe('ready');
  await expect(page.getByText('ready', { exact: true })).toBeVisible();
  expect(reset.simulation_time_ms).toBe(0);
  await expect(message).toHaveValue(
    reset.messages.find((m) => m.id === 'msg-1')!.text!,
  );
  await expect(button('Run')).toBeEnabled();
});

test('reconnects to the same simulation after a WebSocket transport failure', async ({
  page,
  backend,
  request,
}) => {
  const wsUrl = backend.url.replace('http:', 'ws:') + '/ws';
  let active: WebSocketRoute | undefined;
  let liveConnections = 0;
  let rejectReconnect = false;
  // All accepted connections use the actual Python WebSocket. Hold the failure
  // open until the user-visible disconnected/reconnecting state is observed.
  await page.routeWebSocket(wsUrl, (route) => {
    if (rejectReconnect) {
      void route.close({ code: 4001, reason: 'Transport unavailable' });
      return;
    }
    route.connectToServer();
    active = route;
    liveConnections++;
  });
  await connect(page, backend.url);
  const id = await createSimulation(page, backend);
  await expect.poll(() => liveConnections).toBeGreaterThan(0);
  const connectionsBefore = liveConnections;
  rejectReconnect = true;
  await active!.close({ code: 4001, reason: 'Injected transport failure' });
  await expect(
    page
      .getByText(/reconnecting|connection lost|backend disconnected/i)
      .first(),
  ).toBeVisible();
  const response = await request.put(
    backend.url + '/api/simulations/' + id + '/messages',
    {
      data: {
        messages: { 'msg-1': 'Edited while the socket was disconnected.' },
      },
    },
  );
  expect(response.ok()).toBe(true);
  rejectReconnect = false;
  await expect
    .poll(() => liveConnections, { timeout: 15000 })
    .toBeGreaterThan(connectionsBefore);
  await expect(
    page.getByLabel('Message text msg-1', { exact: true }),
  ).toHaveValue('Edited while the socket was disconnected.');
  expect((await backend.state(id)).epoch).toBe(0);
});
