import { createServer } from 'node:http';
import { createReadStream } from 'node:fs';
import { stat, readFile } from 'node:fs/promises';
import { resolve, extname, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { renderHtml } from './metadata.mjs';
import { websiteMiddleware } from './middleware.mjs';

const root = fileURLToPath(new URL('../dist/', import.meta.url));
const content = websiteMiddleware(process.env, async (website, page) =>
  renderHtml(await readFile(resolve(root, 'index.html'), 'utf8'), website, page, process.env));
const mime = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
};

const server = createServer((request, response) => {
  response.setHeader('X-Content-Type-Options', 'nosniff');
  response.setHeader('Referrer-Policy', 'same-origin');
  content(request, response, async () => {
    if (!['GET', 'HEAD'].includes(request.method)) {
      response.writeHead(405, { Allow: 'GET, HEAD' });
      response.end();
      return;
    }
    let path;
    try {
      path = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
    } catch {
      response.writeHead(400);
      response.end();
      return;
    }
    const file = resolve(root, '.' + (path === '/' ? '/index.html' : path));
    if (!file.startsWith(resolve(root) + sep)) {
      response.writeHead(404);
      response.end();
      return;
    }
    try {
      const info = await stat(file);
      if (!info.isFile()) throw new Error('Not a file.');
      response.writeHead(200, {
        'Content-Type': mime[extname(file)] ?? 'application/octet-stream',
        'Content-Length': info.size,
        'Cache-Control': response.getHeader('Cache-Control') || (path.startsWith('/assets/') ? 'public, max-age=31536000, immutable' : 'no-cache'),
      });
      if (request.method === 'HEAD') response.end();
      else createReadStream(file).on('error', () => response.destroy()).pipe(response);
    } catch {
      response.writeHead(404);
      response.end('Not found.');
    }
  });
});
server.listen(Number(process.env.PORT ?? 5174), '0.0.0.0', () => console.log('Example website is listening on port ' + (process.env.PORT ?? 5174)));
for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => server.close(() => process.exit(0)));
}
