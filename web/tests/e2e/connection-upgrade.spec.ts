import { expect, test } from './backend';

test('recovers from a Tor-only connection and opens configuration on a current backend with an existing run', async ({
  page,
  backend,
  request,
}) => {
  const config = await (await request.get(backend.url + '/api/config')).json();
  const state = await (
    await request.post(backend.url + '/api/simulations', { data: config })
  ).json();
  // Reserve two virtual endpoints so the test is independent of other local simulators.
  const current = 'http://127.0.0.1:8001',
    legacy = 'http://127.0.0.1:8099';
  await page.route(/^http:\/\/127\.0\.0\.1:80\d\d\//, async (route) => {
    const { origin, pathname } = new URL(route.request().url());
    if (origin === current) {
      const response = await request.get(backend.url + pathname);
      await route.fulfill({ response });
    } else if (origin === legacy && pathname === '/health') {
      await route.fulfill({
        json: {
          service: 'simulation-backend',
          status: 'ok',
          api_version: '1',
          simulation_id: null,
        },
      });
    } else if (origin === legacy && pathname === '/api/config') {
      const old = { ...config };
      delete old.sender_channel;
      delete old.recipient_channel;
      await route.fulfill({ json: old });
    } else await route.abort('connectionrefused');
  });
  await page.routeWebSocket(
    /^ws:\/\/127\.0\.0\.1:(8001|8099)\/ws$/,
    (socket) => {
      socket.onMessage((raw) => {
        const command = JSON.parse(String(raw));
        if (command.type === 'subscribe')
          socket.send(
            JSON.stringify({
              type: 'snapshot',
              state,
              history_after: 0,
              events: [],
            }),
          );
      });
      socket.send(JSON.stringify({ type: 'backend_ready', api_version: '1' }));
    },
  );
  const connect = async () => {
    await page
      .getByRole('button', { name: 'Test connection', exact: true })
      .click();
    await page.getByRole('button', { name: 'Connect', exact: true }).click();
  };
  await page.goto('/?port=8099');
  await connect();
  await expect(page.getByText(/only supports Tor/)).toBeVisible();
  await page
    .getByRole('button', { name: 'Find and connect to updated backend' })
    .click();
  const sender = page.getByLabel('Sender channel', { exact: true }),
    recipient = page.getByLabel('Recipient channel', { exact: true });
  await expect(sender).toBeEnabled();
  await sender.selectOption('shadowsocks');
  await recipient.selectOption('direct');
  await expect(sender).toHaveValue('shadowsocks');
  await expect(recipient).toHaveValue('direct');
  expect(new URL(page.url()).searchParams.get('port')).toBe('8001');
  expect(new URL(page.url()).searchParams.get('setup')).toBe('1');
  await page.reload();
  await connect();
  await expect(
    page.getByRole('button', { name: 'Create simulation', exact: true }),
  ).toBeVisible();
  expect((await backend.state(state.simulation_id)).status).toBe('ready');
});
