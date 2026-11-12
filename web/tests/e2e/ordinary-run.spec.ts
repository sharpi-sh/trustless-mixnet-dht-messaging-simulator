import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import type { WebSocketRoute } from '@playwright/test';
import { connect, createSimulation, expect, test } from './backend';

test('ordinary Run moves Alice’s packet and keeps the first transit selectable during the next hop and across reconnect', async ({
  page,
  backend,
  request,
}) => {
  test.setTimeout(90_000);
  await page.setViewportSize({ width: 1600, height: 1000 });
  const sockets: WebSocketRoute[] = [];
  await page.routeWebSocket(
    backend.url.replace('http:', 'ws:') + '/ws',
    (route) => {
      route.connectToServer();
      sockets.push(route);
    },
  );
  await connect(page, backend.url);
  const id = await createSimulation(page, backend);
  const sender =
    '[data-message-id="msg-1"][data-source="sender-1"][data-target="tor-sender-1"]';
  const firstMarker = '[data-transit-id]' + sender;
  // Sample before clicking Run so the first real departure cannot be missed.
  const motion = page.evaluate(
    (selector) =>
      new Promise<{ id: string; distance: number }>((resolve) => {
        let id = '',
          x = 0,
          y = 0;
        function sample() {
          const element = document.querySelector<SVGGElement>(selector);
          const matrix = element?.transform.baseVal.getItem(0).matrix;
          if (matrix && element) {
            const transit = element.dataset.transitId!;
            if (transit !== id) {
              id = transit;
              x = matrix.e;
              y = matrix.f;
            }
            const scale = element.getScreenCTM()?.a ?? 1;
            const distance = Math.hypot(matrix.e - x, matrix.f - y) * scale;
            if (distance >= 2) {
              resolve({ id, distance });
              return;
            }
          }
          requestAnimationFrame(sample);
        }
        requestAnimationFrame(sample);
      }),
    firstMarker,
  );
  const button = (name: string) =>
    page.getByRole('button', { name, exact: true });
  await button('Run').click();
  const movement = await motion;
  expect(movement.distance).toBeGreaterThanOrEqual(2);
  const next =
    '[data-message-id="msg-1"][data-source="tor-sender-1"][data-target="provider-west"]';
  const nextMarker = page.locator('[data-transit-id]' + next);
  await nextMarker.waitFor({ state: 'attached', timeout: 30_000 });
  const first = page.locator('[data-message-path]' + sender);
  const dot = first.locator('[data-history-leg="' + movement.id + '"]');
  await expect(first).toHaveAttribute('data-leg-status', 'completed');
  // Click the actual retained SVG symbol with the simulation still running.
  await dot.click();
  const readout = page.locator('[data-selected-leg="' + movement.id + '"]');
  await expect(
    readout.getByText('Sphinx packet', { exact: true }),
  ).toBeVisible();
  await button('Pause').click();
  await expect
    .poll(async () => (await backend.state(id)).status)
    .toBe('paused');
  await expect(page.locator('[data-message-path]' + next)).toBeAttached();

  const snapshot = await backend.state(id);
  const response = await request.get(
    backend.url + '/api/simulations/' + id + '/events',
    {
      params: { after: snapshot.first_message_hop_sequence! - 1, limit: 1 },
    },
  );
  const departure = (await response.json()).events[0];
  expect(departure.payload.transit_id).toBe(movement.id);
  await expect(
    readout.getByText(departure.payload.cargo.sha256, { exact: true }),
  ).toBeVisible();

  const before = sockets.length;
  await sockets
    .at(-1)!
    .close({ code: 4001, reason: 'Reconnect during route inspection' });
  await expect
    .poll(() => sockets.length, { timeout: 15000 })
    .toBeGreaterThan(before);
  await expect(page.getByRole('status')).toHaveText('Backend connected');
  await expect(first).toHaveCount(1);
  await dot.click();
  await expect(
    readout.getByText(departure.payload.cargo.sha256, { exact: true }),
  ).toBeVisible();
  const directory = process.env.SIM_GRAPH_EVIDENCE;
  if (directory) {
    await mkdir(directory, { recursive: true });
    const graph = page.locator('section.network-panel');
    await graph.screenshot({
      path: join(directory, 'ordinary-run-first-transit.png'),
    });
  }
});
