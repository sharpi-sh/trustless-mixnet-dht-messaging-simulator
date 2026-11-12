import { render } from 'svelte/server';
import { expect, test } from 'vitest';
import Page from './+page.svelte';

test('renders a disconnected laboratory without a backend', () => {
  const { body } = render(Page);
  expect(body).toContain('Messaging network laboratory');
  expect(body).toContain('Backend disconnected');
});

test('requires an explicit endpoint before enabling the configuration workspace', () => {
  const { body } = render(Page);
  expect(body).toContain('Backend endpoint');
  expect(body).toContain('Test connection');
  expect(body).not.toContain('127.0.0.1:8000');
  expect(body).not.toContain('Create simulation');
  expect(body).not.toContain('data-node-id');
});
