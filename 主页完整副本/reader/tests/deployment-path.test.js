import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..');

test('production API scans source inside the uploaded application root', async () => {
  const api = await readFile(resolve(root, 'api.php'), 'utf8');
  assert.match(api, /realpath\(__DIR__ \. '\/source'\)/);
  assert.doesNotMatch(api, /\.\.\/reader\/source/);
});

test('production API returns URLs relative to the application root', async () => {
  const api = await readFile(resolve(root, 'api.php'), 'utf8');
  assert.match(api, /return 'source\/'/);
});

test('deployment guide documents the required series folder layout', async () => {
  const readme = await readFile(resolve(root, 'README.md'), 'utf8');
  assert.match(readme, /source\/系列名\/.*\.pdf/);
});
