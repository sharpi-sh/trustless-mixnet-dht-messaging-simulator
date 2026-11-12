import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { expect, test } from 'vitest';
import { avatarUrl } from './avatars';

test('every supported participant has a distinct bundled JPEG portrait', () => {
  const portraits = new Set<string>();
  for (const role of ['sender', 'receiver']) {
    for (let index = 1; index <= 10; index++) {
      const url = avatarUrl(`${role}-${index}`);
      expect(url).toMatch(/^\/avatars\/[\w-]+\.jpg$/);
      const data = readFileSync(join('static', url));
      expect([...data.subarray(0, 3)]).toEqual([0xff, 0xd8, 0xff]);
      portraits.add(data.toString('base64'));
    }
  }
  expect(portraits.size).toBe(20);
});
