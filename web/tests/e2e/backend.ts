import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { setTimeout as delay } from 'node:timers/promises';
import { expect, test as base, type Page } from '@playwright/test';
import type { Snapshot } from '../../src/lib/types';

type Backend = {
  url: string;
  state: (id: string) => Promise<Snapshot>;
};

export const test = base.extend<{ backend: Backend }>({
  backend: async ({ request }, use) => {
    const root = fileURLToPath(new URL('../../../', import.meta.url));
    // Python binds port zero itself and prints the socket's assigned port.
    const child = spawn(
      './.venv/bin/python',
      ['python/main.py', '--first-port', '0', '--last-port', '0'],
      { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] },
    );
    const closed = new Promise<void>((resolve) =>
      child.once('close', () => resolve()),
    );
    let output = '';
    let failure = '';
    let url = '';
    child.on('error', (error) => {
      failure = error.message;
    });
    child.once('exit', (code, signal) => {
      failure = `Python exited (${signal ?? code}).`;
    });
    child.stdout.setEncoding('utf8');
    child.stderr.setEncoding('utf8');
    child.stdout.on('data', (chunk: string) => {
      output = (output + chunk).slice(-8192);
      url ||= output.match(/HTTP API: (http:\/\/127\.0\.0\.1:\d+)/)?.[1] ?? '';
    });
    child.stderr.on('data', (chunk: string) => {
      output = (output + chunk).slice(-8192);
    });
    try {
      const deadline = Date.now() + 15_000;
      let ready = false;
      while (!ready && !failure && Date.now() < deadline) {
        if (url) {
          try {
            ready = (
              await request.get(`${url}/health`, { timeout: 1000 })
            ).ok();
          } catch {
            /* Uvicorn is still starting after the socket announcement. */
          }
        }
        if (!ready) await delay(75);
      }
      if (!ready)
        throw new Error(
          `Python backend failed to start. ${failure}\n${output}`,
        );
      await use({
        url,
        state: async (id: string) => {
          const response = await request.get(
            `${url}/api/simulations/${encodeURIComponent(id)}`,
          );
          expect(response.ok()).toBe(true);
          return response.json();
        },
      });
    } finally {
      if (child.exitCode === null && child.signalCode === null) {
        child.kill('SIGTERM');
        const hardStop = setTimeout(() => child.kill('SIGKILL'), 3000);
        try {
          await closed;
        } finally {
          clearTimeout(hardStop);
        }
      }
    }
  },
});

export { expect };

export async function connect(page: Page, url: string): Promise<void> {
  await page.goto('/');
  await page.getByLabel('Backend endpoint', { exact: true }).fill(url);
  await page
    .getByRole('button', { name: 'Test connection', exact: true })
    .click();
  await expect(page.getByRole('status')).toHaveText('Backend tested');
  const button = page.getByRole('button', { name: 'Connect', exact: true });
  await expect(button).toBeEnabled();
  await button.click();
  await expect(page.getByRole('status')).toHaveText('Backend connected');
  await expect(
    page.getByRole('button', { name: 'Create simulation', exact: true }),
  ).toBeVisible();
}

export async function createSimulation(
  page: Page,
  backend: Backend,
): Promise<string> {
  const response = page.waitForResponse(
    (r) =>
      r.url() === backend.url + '/api/simulations' &&
      r.request().method() === 'POST',
  );
  await page
    .getByRole('button', { name: 'Create simulation', exact: true })
    .click();
  const created = await response;
  expect(created.status()).toBe(201);
  const state = (await created.json()) as Snapshot;
  await expect(
    page.getByRole('button', { name: 'Run', exact: true }),
  ).toBeVisible();
  return state.simulation_id;
}
