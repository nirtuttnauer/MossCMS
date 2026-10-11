import { loadWebsite } from './moss.mjs';
import { loadPreview, applyPreview, PreviewError } from './preview.mjs';
import { routePage, pagePath } from '../../shared/routes.mjs';

// Dev delegates known routes to Vite; production supplies its built HTML template.
export function pageMiddleware(environment, template) {
  return async (request, response, next) => {
    const path = new URL(request.url, 'http://localhost').pathname;
    if (
      path.startsWith('/@') || path.startsWith('/src/') || path.startsWith('/node_modules/') ||
      path.startsWith('/api/') || path.startsWith('/assets/') || /\.[a-zA-Z0-9]+$/.test(path)
    ) return next();
    if (!['GET', 'HEAD'].includes(request.method)) return next();
    try {
      const preview = await loadPreview(request, environment);
      let website = await loadWebsite(environment);
      if (preview) website = applyPreview(website, preview);
      const page = routePage(website.pages, path, preview ? [] : website.redirects, preview ? [] : website.reservedPaths);
      response.setHeader('Cache-Control', 'no-store');
      if (!page) {
        response.writeHead(404, { 'Content-Type': 'text/html; charset=utf-8', 'X-Robots-Tag': 'noindex' });
        response.end('<!doctype html><title>Page not found</title><h1>Page not found</h1><a href="/">Home</a>');
        return;
      }
      const canonical = pagePath(page);
      if (canonical !== path) {
        response.writeHead(308, { Location: canonical });
        response.end();
        return;
      }
      if (!template) return next();
      response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      response.end(request.method === 'HEAD' ? '' : await template(website, page));
    } catch (error) {
      response.writeHead(error instanceof PreviewError ? 401 : 503, {
        'Content-Type': 'text/plain',
        'Cache-Control': 'no-store',
      });
      response.end('Content temporarily unavailable.');
    }
  };
}
