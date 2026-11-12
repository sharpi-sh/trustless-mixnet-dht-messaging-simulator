import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import type { Locator, Page } from '@playwright/test';
import { connect, createSimulation, expect, test } from './backend';
import type { LabNode } from '../../src/lib/types';

async function assertGeometry(nodes: Locator, topology: LabNode[]) {
  const cards = await nodes.evaluateAll((groups) =>
    groups.map((group) => {
      const rect = group.querySelector('[data-card]');
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
async function assertFit(viewport: Locator) {
  await expect
    .poll(async () =>
      viewport.evaluate((container) => {
        const world = container.querySelector('svg')!.getBoundingClientRect();
        return Math.max(
          Math.abs(world.width - container.clientWidth),
          Math.abs(world.height - container.clientHeight),
        );
      }),
    )
    .toBeLessThan(1);
  const bounds = await viewport.evaluate((container) => {
    const viewportBox = container.getBoundingClientRect();
    const cards = Array.from(
      container.querySelectorAll('[data-card]'),
      (card) => card.getBoundingClientRect(),
    );
    const sample = container.querySelector<SVGRectElement>('rect[data-card]')!;
    const rendered = sample.getBoundingClientRect();
    return {
      horizontalCoverage:
        (Math.max(...cards.map((c) => c.right)) -
          Math.min(...cards.map((c) => c.left))) /
        viewportBox.width,
      verticalCoverage:
        (Math.max(...cards.map((c) => c.bottom)) -
          Math.min(...cards.map((c) => c.top))) /
        viewportBox.height,
      ratio: rendered.width / rendered.height,
      naturalRatio: sample.width.baseVal.value / sample.height.baseVal.value,
    };
  });
  expect(bounds.horizontalCoverage).toBeGreaterThan(0.9);
  expect(bounds.verticalCoverage).toBeGreaterThan(0.76);
  expect(bounds.ratio).toBeCloseTo(bounds.naturalRatio, 3);
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

for (const count of [6, 10, 20]) {
  test(
    'renders ' +
      count +
      ' mixes in ordered columns and inspects the live topology',
    async ({ page, backend }) => {
      await page.setViewportSize({ width: 1500, height: 1000 });
      await connect(page, backend.url);
      const mixes = page.getByLabel('Mix nodes', { exact: true });
      await expect(mixes).toHaveValue('6');
      await expect(mixes).toHaveAttribute('min', '6');
      await mixes.fill(String(count));
      const addSender = page.getByRole('button', {
        name: 'Add another sender',
        exact: true,
      });
      await addSender.click();
      await addSender.click();
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
      const bands = graph.locator('.band');
      await expect(bands).toHaveCount(
        new Set(
          topology.filter((n) => n.kind !== 'person').map((n) => n.stage_index),
        ).size,
      );
      await expect(graph.locator('.band.person')).toHaveCount(0);
      const mixId = topology.find((n) => n.kind === 'mix')!.id;
      const mixCard = await graph
        .locator('[data-node-id="' + mixId + '"] [data-card]')
        .boundingBox();
      const mixBand = await graph
        .locator('.band.mix rect')
        .first()
        .boundingBox();
      expect(mixCard!.width).toBeLessThan(mixBand!.width / 2);

      const avatars = [];
      for (const device of snapshot.devices) {
        const avatar = graph.locator('[data-node-id="' + device.id + '"]');
        const photo = avatar.locator('image');
        await expect(photo).toBeVisible();
        const href = await photo.getAttribute('href');
        expect(href).toBeTruthy();
        const loaded = await photo.evaluate(async (_, src) => {
          const image = new Image();
          image.src = src!;
          await image.decode();
          return (
            image.naturalWidth > 0 &&
            new URL(image.src).origin === location.origin
          );
        }, href);
        expect(loaded).toBe(true);
        const circle = await avatar.locator('circle[data-card]').boundingBox();
        expect(circle).not.toBeNull();
        expect(circle!.width).toBeCloseTo(circle!.height, 1);
        if (device.role === 'sender') avatars.push(circle!);
        const channelPath = snapshot.topology.paths.find(
          (p) =>
            [p.source_id, p.target_id].includes(device.id) &&
            [p.source_id, p.target_id].includes(device.channel_id!),
        )!;
        await expect(
          graph
            .locator('[data-path-id="' + channelPath.id + '"] path.stroke')
            .first(),
        ).toBeAttached();
      }
      avatars.sort((a, b) => a.y - b.y);
      for (const [i, avatar] of avatars.entries()) {
        expect(avatar.x + avatar.width / 2).toBeCloseTo(
          avatars[0].x + avatars[0].width / 2,
          1,
        );
        if (i)
          expect(
            avatar.y - avatars[i - 1].y - avatars[i - 1].height,
          ).toBeGreaterThan(2);
      }
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
      await assertFit(graphViewport);
      await page.getByRole('button', { name: 'Zoom in', exact: true }).click();
      await expect
        .poll(async () =>
          graphViewport.evaluate((v) => v.scrollWidth / v.clientWidth),
        )
        .toBeGreaterThan(1.1);
      await page
        .getByRole('button', { name: 'Fit graph', exact: true })
        .click();
      await assertFit(graphViewport);
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
      await assertFit(graphViewport);
      await capture(page, 'graph-' + count + '-mixes-fullscreen');
      await page.setViewportSize({ width: 970, height: 620 });
      await assertFit(graphViewport);
      await assertGeometry(nodes, topology);
      await page.setViewportSize({ width: 1500, height: 1000 });
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
