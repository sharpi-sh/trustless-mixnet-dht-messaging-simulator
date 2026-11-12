import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import { connect, createSimulation, expect, test } from './backend';

for (const seed of [null, '2046379413032268']) {
  const scenario = seed ? 'after 1,238 startup steps' : 'with default settings';
  test(
    'ordinary Run moves Alice’s packet and preserves the first transit ' +
      scenario,
    async ({ page, backend, request }) => {
      test.setTimeout(90_000);
      await page.setViewportSize({ width: 1600, height: 1000 });
      // Retain a reference for the reconnect check without proxying startup frames through Playwright.
      await page.addInitScript(() => {
        const send = WebSocket.prototype.send;
        WebSocket.prototype.send = function (data) {
          (
            window as Window & { simulationSocket?: WebSocket }
          ).simulationSocket = this;
          return send.call(this, data);
        };
      });
      let connections = 0;
      page.on('websocket', () => connections++);
      await connect(page, backend.url);
      if (seed)
        await page.getByLabel('Random seed', { exact: true }).fill(seed);
      const id = await createSimulation(page, backend);
      const sender =
        '[data-message-id="msg-1"][data-source="sender-1"][data-target="tor-sender-1"]';
      const firstMarker = '[data-transit-id]' + sender;
      // Sample before clicking Run so the first real departure cannot be missed.
      const motion = page.evaluate(
        (selector) =>
          new Promise<{ id: string; distance: number; observations: number }>(
            (resolve) => {
              let observations = 0,
                maxDistance = 0;
              const began = performance.now();
              let id = '',
                x = 0,
                y = 0;
              function sample() {
                const element = document.querySelector<SVGGElement>(selector);
                const matrix = element?.transform.baseVal.getItem(0).matrix;
                if (matrix && element) {
                  observations++;
                  const transit = element.dataset.transitId!;
                  if (transit !== id) {
                    id = transit;
                    x = matrix.e;
                    y = matrix.f;
                  }
                  const scale = element.getScreenCTM()?.a ?? 1;
                  const distance =
                    Math.hypot(matrix.e - x, matrix.f - y) * scale;
                  maxDistance = Math.max(maxDistance, distance);
                  if (distance >= 2) {
                    resolve({ id, distance, observations });
                    return;
                  }
                }
                if (performance.now() - began > 15000) {
                  resolve({ id, distance: maxDistance, observations });
                  return;
                }
                requestAnimationFrame(sample);
              }
              requestAnimationFrame(sample);
            },
          ),
        firstMarker,
      );
      const button = (name: string) =>
        page.getByRole('button', { name, exact: true });
      await button('Run').click();
      const movement = await motion;
      expect(
        movement,
        'First ordinary Run departure should remain visibly in motion',
      ).toMatchObject({
        id: expect.stringMatching(/^transit-/),
        distance: expect.any(Number),
      });
      expect(
        movement.distance,
        JSON.stringify(movement),
      ).toBeGreaterThanOrEqual(2);
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

      const before = connections;
      await page.evaluate(() => {
        const socket = (window as Window & { simulationSocket: WebSocket })
          .simulationSocket;
        socket.close(4001, 'Reconnect during route inspection');
      });
      await expect
        .poll(() => connections, { timeout: 15000 })
        .toBeGreaterThan(before);
      await expect(
        page.getByText('Backend connected', { exact: true }),
      ).toBeVisible();
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
          path: join(
            directory,
            seed
              ? 'ordinary-run-busy-first-transit.png'
              : 'ordinary-run-first-transit.png',
          ),
        });
      }
    },
  );
}
