import { loadWebsite } from './moss.mjs';
import { pagePath } from '../../shared/routes.mjs';
import { escapeHtml } from './metadata.mjs';

const xml = value => escapeHtml(String(value ?? '').replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g, ''));
const date = value => Number.isFinite(Date.parse(value)) ? new Date(value) : null;

export function sitemap(website) {
  const urls = website.pages.map(page => {
    const publishedAt = date(page.publishedAt);
    return `<url><loc>${xml(new URL(pagePath(page), website.siteUrl).href)}</loc>` +
      (publishedAt ? `<lastmod>${publishedAt.toISOString()}</lastmod>` : '') + '</url>';
  }).join('');
  return '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' +
    urls + '</urlset>';
}

export function rss(website) {
  const posts = website.pages
    .filter(page => page.typeKey === 'sitePost')
    .sort((a, b) => (date(b.publishedAt)?.getTime() || 0) - (date(a.publishedAt)?.getTime() || 0))
    .slice(0, 100);
  const items = posts.map(page => {
    const publishedAt = date(page.publishedAt);
    return [
      `<item><title>${xml(page.title)}</title>`,
      `<link>${xml(new URL(pagePath(page), website.siteUrl).href)}</link>`,
      `<guid isPermaLink="false">${xml('moss:' + page.id)}</guid>`,
      `<description>${xml(page.description || '')}</description>`,
      publishedAt ? `<pubDate>${publishedAt.toUTCString()}</pubDate>` : '',
      '</item>',
    ].join('');
  }).join('');
  return [
    '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>',
    `<title>${xml(website.profile?.name || 'Blog')}</title>`,
    `<link>${xml(website.siteUrl)}</link>`,
    `<description>${xml(website.profile?.headline || 'Blog posts')}</description>`,
    items,
    '</channel></rss>',
  ].join('');
}

export function feedMiddleware(environment) {
  return async (request, response, next) => {
    const path = request.url?.split('?')[0];
    if (!['/sitemap.xml', '/rss.xml'].includes(path)) return next();
    if (!['GET', 'HEAD'].includes(request.method)) {
      response.writeHead(405, { Allow: 'GET, HEAD' });
      response.end();
      return;
    }
    try {
      const website = await loadWebsite(environment);
      const body = path === '/sitemap.xml' ? sitemap(website) : rss(website);
      response.writeHead(200, {
        'Content-Type': 'application/xml; charset=utf-8',
        'Cache-Control': 'no-store',
        'X-Content-Type-Options': 'nosniff',
      });
      response.end(request.method === 'HEAD' ? '' : body);
    } catch {
      response.writeHead(503, { 'Cache-Control': 'no-store' });
      response.end('Feed temporarily unavailable.');
    }
  };
}
