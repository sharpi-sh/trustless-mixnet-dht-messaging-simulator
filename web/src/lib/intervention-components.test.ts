import { render } from 'svelte/server';
import { expect, test } from 'vitest';
import { LabClient } from './api';
import { snapshot, details } from './fixtures/control-state';
import Interventions from './Interventions.svelte';
import Inspector from './Inspector.svelte';
import NetworkGraph from './NetworkGraph.svelte';

const selectedNode = 'receiver-1';
const selectedPath = snapshot.topology.paths.find((p) => p.blocked)!.id;
const controlProps = {
  lab: snapshot,
  selectedNode,
  selectedPath,
  client: new LabClient(),
  connected: true,
};
const inspectProps = {
  lab: snapshot,
  selectedNode,
  selectedPath,
  events: [],
  onNode: () => {},
  onPath: () => {},
  onPeer: () => {},
};

test('selected receiver, blocked path and partial receiver polling are shown from the backend projection', () => {
  const { body } = render(Interventions, { props: controlProps });
  expect(body).toContain('1 of 2 enabled');
  expect(body).toContain('Polling disabled');
  expect(body).toContain('Enable receiver polling');
  expect(body).toContain('Bring node online');
  expect(body).toContain('Restore path');
  for (const name of new Set(snapshot.topology.paths.map((p) => p.boundary)))
    expect(body).toContain(name);
  expect(body).toContain('Drop traffic already in flight');
  expect(body).not.toContain('Take node offline');
});

test('all mutating controls are disabled when the server disconnects or a run is terminal', () => {
  for (const props of [
    { ...controlProps, connected: false },
    { ...controlProps, lab: { ...snapshot, status: 'completed' as const } },
  ]) {
    const { body } = render(Interventions, { props });
    const tags = body.match(/<(?:button|select|input)\b[^>]*>/g) ?? [];
    expect(tags.length).toBeGreaterThan(6);
    expect(tags.every((tag) => /\bdisabled\b/.test(tag))).toBe(true);
  }
  const enabled = render(Interventions, {
    props: { ...controlProps, selectedNode: 'receiver-2', selectedPath: '' },
  }).body;
  expect(enabled).toContain('Disable receiver polling');
  expect(enabled).toContain('Take node offline');
  expect(enabled).not.toContain('Restore path');
});

test('inspectors render device fingerprints, node-specific protocol details and path counters', () => {
  for (const [id, expected] of [
    [
      'receiver-1',
      snapshot.devices.find((d) => d.id === 'receiver-1')!.fingerprint,
    ],
    ['dht-1', 'Routing buckets'],
    ['mix-1', 'Configured adjacency'],
    ['provider-east', 'Sphinx replay tags'],
    ['storage-1', 'Fragment placements'],
    ['tor-receiver-1', 'Entries'],
  ]) {
    const { body } = render(Inspector, {
      props: { ...inspectProps, selectedNode: id, details: details[id] },
    });
    expect(body).toContain(expected);
    expect(body).toContain(details[id].profile.id);
  }
  const pathHtml = render(Inspector, {
    props: { ...inspectProps, selectedNode: '', details: null },
  }).body;
  expect(pathHtml).toContain('Path transit delay');
  expect(pathHtml).toContain('block-return');
  expect(pathHtml).toContain('Dropped');
});

test('graph exposes the projected network as labelled SVG nodes and paths', () => {
  const { body } = render(NetworkGraph, {
    props: { ...inspectProps, details: details[selectedNode] },
  });
  expect(body).toContain('<svg');
  expect(body).toContain('aria-label="Network topology"');
  expect(body).toContain(selectedNode);
  expect(body).toContain('provider-east');
});
