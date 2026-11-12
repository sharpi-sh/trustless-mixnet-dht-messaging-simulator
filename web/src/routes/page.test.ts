import { render } from 'svelte/server';
import { expect, test } from 'vitest';
import Page from './+page.svelte';

test('renders a disconnected laboratory without a backend', () => {
  const { body } = render(Page);
  expect(body).toContain('Messaging network laboratory');
  expect(body).toContain('Backend disconnected');
});
