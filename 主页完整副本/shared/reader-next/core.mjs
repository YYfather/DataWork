const collator = new Intl.Collator('zh-CN', { numeric: true, sensitivity: 'base' });

export function naturalCompare(a, b) {
  return collator.compare(String(a), String(b));
}

export function flattenLibrary(folders = {}) {
  let bytes = 0;
  let total = 0;
  const collections = Object.entries(folders)
    .map(([name, books]) => ({
      name,
      books: [...books]
        .map((book) => {
          bytes += Number(book.size) || 0;
          total += 1;
          return { ...book, collection: name };
        })
        .sort((a, b) => naturalCompare(a.name, b.name)),
    }))
    .sort((a, b) => naturalCompare(b.name, a.name));
  return { collections, total, bytes };
}

export function filterLibrary(collections, query) {
  const needle = String(query || '').trim().toLocaleLowerCase('zh-CN');
  if (!needle) return collections;
  return collections.flatMap((collection) => {
    if (collection.name.toLocaleLowerCase('zh-CN').includes(needle)) return [collection];
    const books = collection.books.filter((book) =>
      book.name.toLocaleLowerCase('zh-CN').includes(needle),
    );
    return books.length ? [{ ...collection, books }] : [];
  });
}

export function clampProgress(page, pageCount) {
  const max = Math.max(1, Number(pageCount) || 1);
  const value = Number.isFinite(Number(page)) ? Math.round(Number(page)) : 1;
  return Math.min(max, Math.max(1, value));
}

export function progressStorageKey(filePath) {
  return `reader-next:progress:${filePath}`;
}
