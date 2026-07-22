import { createServer } from 'node:http';
import { readFile, readdir, stat } from 'node:fs/promises';
import { extname, join, normalize, relative, resolve, sep } from 'node:path';

const port = Number(process.env.PORT || 8765);
const appRoot = resolve(import.meta.dirname);
const workspaceRoot = resolve(appRoot, '..');
const sourceRoot = resolve(workspaceRoot, 'reader', 'source');
const mime = {
  '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8', '.pdf': 'application/pdf',
};

async function scan(dir = sourceRoot, folder = '') {
  const files = [];
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    const relativePath = folder ? `${folder}/${entry.name}` : entry.name;
    if (entry.isDirectory()) files.push(...await scan(path, relativePath));
    else if (entry.isFile() && extname(entry.name).toLowerCase() === '.pdf') {
      const info = await stat(path);
      files.push({
        name: entry.name.slice(0, -4), path: relativePath,
        url: `source/${relativePath.split('/').map(encodeURIComponent).join('/')}`,
        folder: folder || '未分类', size: info.size, modified: info.mtime.toISOString(),
      });
    }
  }
  return files;
}

function safePath(root, requestPath) {
  const target = normalize(resolve(root, requestPath));
  return target === root || target.startsWith(`${root}${sep}`) ? target : null;
}

createServer(async (request, response) => {
  try {
    const url = new URL(request.url, `http://${request.headers.host}`);
    if (url.pathname === '/reader/api.php') {
      const grouped = {};
      for (const file of await scan()) (grouped[file.folder] ||= []).push(file);
      response.writeHead(200, { 'Content-Type': mime['.json'], 'Cache-Control': 'no-store' });
      response.end(JSON.stringify({ ok: true, folders: grouped }));
      return;
    }
    const decoded = decodeURIComponent(url.pathname);
    const root = decoded.startsWith('/reader/source/') ? workspaceRoot : appRoot;
    const requestPath = decoded.startsWith('/reader/source/')
      ? decoded.slice(1)
      : decoded.replace(/^\/reader\/?/, '') || 'index.html';
    const filePath = safePath(root, requestPath);
    if (!filePath) throw new Error('Invalid path');
    const body = await readFile(filePath);
    response.writeHead(200, { 'Content-Type': mime[extname(filePath)] || 'application/octet-stream' });
    response.end(body);
  } catch {
    response.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
    response.end('Not found');
  }
}).listen(port, '127.0.0.1', () => {
  console.log(`Reader: http://127.0.0.1:${port}/reader/`);
});

