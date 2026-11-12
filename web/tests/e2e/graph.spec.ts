import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import type { Locator, Page } from '@playwright/test';
import { connect, createSimulation, expect, test } from './backend';
import type { LabNode } from '../../src/lib/types';

async function assertGeometry(nodes: Locator, topology: LabNode[]) {
  const cards = await nodes.evaluateAll((groups) =>
    groups.map((group) => {
      const rect = group.querySelector('rect[data-card]');
      if (!rect)
        throw new Error(
          'Missing card for ' + group.getAttribute('data-node-id'),
        );
      const { left, right, top, bottom, width, height } =
        rect.getBoundingClientRect();
      return {
        id: group.getAttribute('data-node-id')!,
        left,
        right,
        top,
        bottom,
        width,
        height,
      };
    }),
  );
  const stage = new Map(topology.map((node) => [node.id, node.stage_index]));
  expect(cards.map((card) => card.id).sort()).toEqual([...stage.keys()].sort());
  for (let i = 0; i < cards.length; i++) {
    const a = cards[i];
    expect(a.width).toBeGreaterThan(0);
    expect(a.height).toBeGreaterThan(0);
    for (const b of cards.slice(i + 1)) {
      const leftStage = stage.get(a.id)!;
      const rightStage = stage.get(b.id)!;
      const overlapX = Math.min(a.right, b.right) - Math.max(a.left, b.left);
      const overlapY = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      expect(
        Math.min(overlapX, overlapY),
        a.id + ' overlaps ' + b.id,
      ).toBeLessThanOrEqual(0.5);
      if (leftStage !== rightStage) {
        const [left, right] = leftStage < rightStage ? [a, b] : [b, a];
        expect(
          left.right,
          left.id + ' crosses ' + right.id,
        ).toBeLessThanOrEqual(right.left + 0.5);
      }
    }
  }
}
async function capture(page: Page, name: string) {
  const directory = process.env.SIM_GRAPH_EVIDENCE;
  if (!directory) return;
  await mkdir(directory, { recursive: true });
  await page.screenshot({
    path: join(directory, name + '.png'),
    animations: 'disabled',
  });
}

for (const count of [10, 20]) {
  test(
    'renders ' +
      count +
      ' mixes in ordered columns and inspects the live topology',
    async ({ page, backend }) => {
      await page.setViewportSize({ width: 1500, height: 1000 });
      await connect(page, backend.url);
      await page.getByLabel('Mix nodes', { exact: true }).fill(String(count));
      await page.getByLabel('Senders', { exact: true }).fill('3');
      await page.getByLabel('Random seed', { exact: true }).fill('32');
      const id = await createSimulation(page, backend);
      const snapshot = await backend.state(id);
      const topology = snapshot.topology.nodes;
      expect(topology.filter((node) => node.kind === 'mix')).toHaveLength(
        count,
      );
      const graph = page.getByRole('group', {
        name: 'Network topology',
        exact: true,
      });
      const nodes = graph.locator('[data-node-id]');
      await expect(nodes).toHaveCount(topology.length);
      await assertGeometry(nodes, topology);
      const sender = page.getByRole('complementary', {
        name: 'Sender conversations',
        exact: true,
      });
      const recipient = page.getByRole('complementary', {
        name: 'Recipient conversations',
        exact: true,
      });
      await expect(sender).toBeVisible();
      await expect(recipient).toBeVisible();
      const graphViewport = page.getByRole('region', {
        name: 'Pan network diagram',
      });
      const [left, diagram, right] = await Promise.all([
        sender.boundingBox(),
        graphViewport.boundingBox(),
        recipient.boundingBox(),
      ]);
      expect(left!.x + left!.width).toBeLessThanOrEqual(diagram!.x + 1);
      expect(diagram!.x + diagram!.width).toBeLessThanOrEqual(right!.x + 1);
      const full = page.getByRole('button', {
        name: 'Full screen',
        exact: true,
      });
      const close = page.getByRole('button', {
        name: 'Close full screen',
        exact: true,
      });
      await full.click();
      await expect(close).toBeVisible();
      await expect(sender).toBeHidden();
      await expect(recipient).toBeHidden();
      const maximised = await page
        .getByRole('region', { name: 'Network topology', exact: true })
        .boundingBox();
      expect(maximised!.width).toBeGreaterThanOrEqual(1499);
      expect(maximised!.height).toBeGreaterThanOrEqual(999);
      await close.click();
      await expect(full).toBeVisible();
      await full.click();
      await page.keyboard.press('Escape');
      await expect(full).toBeFocused();
      await expect(sender).toBeVisible();
      for (const device of snapshot.devices) {
        await expect(
          graph.locator('[data-node-id="' + device.id + '"]'),
        ).toHaveCount(1);
      }

      await graph.scrollIntoViewIfNeeded();
      await capture(page, 'graph-' + count + '-mixes-native');
      await page
        .getByRole('button', { name: 'Fit graph', exact: true })
        .click();
      await graph.scrollIntoViewIfNeeded();
      await capture(page, 'graph-' + count + '-mixes-fit');
      const card = (id: string) => graph.locator('[data-node-id="' + id + '"]');
      const inspector = page.getByRole('complementary', {
        name: 'Node inspector',
        exact: true,
      });
      const mix = topology.find((node) => node.kind === 'mix')!;
      await card(mix.id).click();
      await expect(inspector).toBeVisible();
      const selectProtocol = () =>
        inspector
          .getByRole('tab', { name: 'Protocol state', exact: true })
          .click();
      await selectProtocol();
      await expect(
        inspector
          .getByText('Mixnet — Loopix (USENIX 2017) loopix-usenix-2017', {
            exact: true,
          })
          .first(),
      ).toBeVisible();
      const peerId = Object.keys(mix.adjacent_peers!)[0];
      await inspector
        .getByRole('button', { name: 'Highlight peer ' + peerId, exact: true })
        .click();
      await expect(card(peerId)).toHaveAttribute('aria-pressed', 'true');

      const dht = topology.find((n) => n.kind === 'dht')!;
      await card(dht.id).click();
      await selectProtocol();
      await expect(
        inspector.getByRole('heading', {
          name: 'Routing buckets',
          exact: true,
        }),
      ).toBeVisible();
      const vault = topology.find((n) => n.kind === 'storage')!;
      await card(vault.id).click();
      await selectProtocol();
      await expect(
        inspector.getByRole('heading', {
          name: 'Fragment placements',
          exact: true,
        }),
      ).toBeVisible();
      const person = snapshot.devices[0];
      await card(person.id).click();
      await selectProtocol();
      await expect(
        inspector.getByRole('heading', { name: 'Device log', exact: true }),
      ).toBeVisible();
      await expect(
        inspector.getByText(person.fingerprint, { exact: true }),
      ).toBeVisible();
      await graph.scrollIntoViewIfNeeded();
      await capture(page, 'graph-' + count + '-mixes-device');
    },
  );
}
