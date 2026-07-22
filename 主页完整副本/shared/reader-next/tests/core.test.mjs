import test from 'node:test';
import assert from 'node:assert/strict';
import {
  naturalCompare,
  flattenLibrary,
  filterLibrary,
  clampProgress,
  progressStorageKey,
} from '../core.mjs';

test('naturalCompare keeps numbered book titles in reading order', () => {
  const titles = ['第10册', '第2册', '第1册'];
  assert.deepEqual(titles.sort(naturalCompare), ['第1册', '第2册', '第10册']);
});

test('flattenLibrary preserves collection names and computes totals', () => {
  const result = flattenLibrary({
    '查理九世': [{ name: '黑贝街的亡灵', path: 'a.pdf', size: 1024 }],
    '怪物大师': [{ name: '怪物果实', path: 'b.pdf', size: 2048 }],
  });
  assert.equal(result.total, 2);
  assert.equal(result.bytes, 3072);
  assert.equal(result.collections[0].name, '怪物大师');
  assert.equal(result.collections[0].books[0].collection, '怪物大师');
});

test('filterLibrary matches book title or collection without case sensitivity', () => {
  const library = flattenLibrary({
    'Mystery': [{ name: 'Black Street', path: 'a.pdf', size: 1 }],
    'Adventure': [{ name: 'Titan City', path: 'b.pdf', size: 1 }],
  });
  assert.equal(filterLibrary(library.collections, 'black')[0].books.length, 1);
  assert.equal(filterLibrary(library.collections, 'ADVENTURE')[0].name, 'Adventure');
});

test('clampProgress bounds invalid page values', () => {
  assert.equal(clampProgress(0, 100), 1);
  assert.equal(clampProgress(120, 100), 100);
  assert.equal(clampProgress(Number.NaN, 100), 1);
});

test('progressStorageKey is stable and isolated per file', () => {
  assert.equal(progressStorageKey('folder/a.pdf'), 'reader-next:progress:folder/a.pdf');
});
