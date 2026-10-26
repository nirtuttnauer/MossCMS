import { randomBytes, createHash } from 'node:crypto';
import { pagePath } from '../../shared/routes.mjs';
import { readBody } from './request-body.mjs';

const sessions = new Map();
const supported = new Set(['sitePage', 'siteProject', 'sitePost', 'siteProfile', 'siteSlide']);
const MAX_SESSIONS = 1000;
const MAX_REQUEST_BYTES = 2048;
export class PreviewError extends Error {}
const hash = value => createHash('sha256').update(value).digest('hex');

function cookie(request) {
  return request.headers.cookie?.split(';')
    .map(value => value.trim())
    .find(value => value.startsWith('moss_preview='))?.slice(13);
}

export const isPreviewRequest = request => Boolean(cookie(request));

function previewHeaders(response) {
  response.setHeader('Cache-Control', 'no-store');
  response.setHeader('X-Robots-Tag', 'noindex, nofollow');
  response.setHeader('Referrer-Policy', 'no-referrer');
  response.setHeader('X-Content-Type-Options', 'nosniff');
}

function sessionCookie(environment, value, seconds = 900) {
  const secure = new URL(environment.SITE_PUBLIC_URL || 'http://localhost:5174').protocol === 'https:';
  return `moss_preview=${value}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${seconds}${secure ? '; Secure' : ''}`;
}

export async function redeemPreview(environment, token) {
  const response = await fetch(new URL('/api/preview/redeem', environment.MOSS_API_URL || 'http://localhost:8001'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${environment.MOSS_DELIVERY_TOKEN}` },
    body: JSON.stringify({ token }),
    signal: AbortSignal.timeout(10000),
  });
  if (!response.ok) {
    throw new PreviewError('Preview expired, revoked or unavailable. Return to the editor to create a new preview.');
  }
  const result = await response.json();
  const expires = Date.parse(result.expiresAt);
  if (!supported.has(result.entry?.typeKey) || !Number.isFinite(expires) || expires <= Date.now()) {
    throw new PreviewError('Preview is out of scope or expired.');
  }
  return result;
}

export async function loadPreview(request, environment) {
  const id = cookie(request);
  if (!id) return null;
  const key = hash(id);
  const session = sessions.get(key);
  if (!session || session.expires <= Date.now()) {
    if (session) sessions.delete(key);
    throw new PreviewError('Preview session expired. Exit preview or create a new one.');
  }
  return redeemPreview(environment, session.token);
}

export function applyPreview(website, preview) {
  const entry = preview.entry;
  const value = { ...entry.data, id: entry.id, slug: entry.slug, resolvedAssets: entry.resolvedAssets };
  if (entry.typeKey === 'siteProfile') website.profile = value;
  else if (entry.typeKey === 'siteSlide') website.slides = [{ ...value, enabled: true }];
  else {
    if (entry.typeKey === 'sitePost' || entry.typeKey === 'siteProject') {
      const parent = entry.typeKey === 'sitePost' ? 'blog' : 'projects';
      value.slug = `${parent}/${entry.slug}`;
      value.parentSlug = website.pages.find(page => page.kind === parent)?.slug || parent;
      value.kind = 'page';
    }
    website.pages = [...website.pages.filter(page => page.id !== entry.id), value];
  }
  website.preview = { entryId: entry.id, revision: preview.revision, expiresAt: preview.expiresAt };
  return website;
}

export function previewPath(entry) {
  const slug = entry.typeKey === 'sitePost' ? `blog/${entry.slug}`
    : entry.typeKey === 'siteProject' ? `projects/${entry.slug}`
    : entry.typeKey === 'sitePage' ? entry.slug : 'home';
  return pagePath({ slug });
}

async function jsonBody(request) {
  return JSON.parse((await readBody(request, MAX_REQUEST_BYTES)).toString());
}

export function previewMiddleware(environment) {
  return async (request, response, next) => {
    const path = request.url?.split('?')[0];
    if (isPreviewRequest(request)) previewHeaders(response);
    if (!['/preview', '/api/preview', '/api/preview/exit'].includes(path)) return next();
    previewHeaders(response);
    const expected = path === '/preview' ? 'GET' : 'POST';
    if (request.method !== expected) {
      response.writeHead(405, { Allow: expected });
      response.end();
      return;
    }
    if (path === '/preview') {
      const nonce = randomBytes(16).toString('base64');
      response.setHeader('Content-Type', 'text/html; charset=utf-8');
      const ancestor = new URL(environment.MOSS_API_URL || 'http://localhost:8001').origin
      response.setHeader('Content-Security-Policy', `default-src 'none'; script-src 'nonce-${nonce}'; connect-src 'self'; base-uri 'none'; frame-ancestors ${ancestor}`);
      response.end(`<!doctype html><html><head>
<meta name="robots" content="noindex,nofollow"><title>Opening preview</title>
</head><body><p>Opening saved preview…</p><script nonce="${nonce}">
const token = new URLSearchParams(location.hash.slice(1)).get('grant');
history.replaceState(null, '', '/preview');
fetch('/api/preview', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ token })
}).then(async response => {
  if (!response.ok) throw new Error('Preview unavailable. Return to the editor and create a new preview.');
  const data = await response.json();
  location.replace(data.path);
}).catch(error => document.querySelector('p').textContent = error.message);
</script></body></html>`);
      return;
    }
    const origins = new Set([
      new URL(environment.SITE_PUBLIC_URL || 'http://localhost:5174').origin,
      ...(environment.SITE_PREVIEW_ORIGINS || 'http://localhost:5174').split(','),
    ]);
    if (request.headers.origin && !origins.has(request.headers.origin)) {
      response.writeHead(403);
      response.end();
      return;
    }
    response.setHeader('Content-Type', 'application/json; charset=utf-8');
    if (path === '/api/preview/exit') {
      const id = cookie(request);
      if (id) sessions.delete(hash(id));
      response.setHeader('Set-Cookie', sessionCookie(environment, '', 0));
      response.end('{}');
      return;
    }
    if (!request.headers['content-type']?.startsWith('application/json')) {
      response.writeHead(415);
      response.end('{}');
      return;
    }
    try {
      const body = await jsonBody(request);
      if (typeof body.token !== 'string' || body.token.length < 20 || body.token.length > 100) {
        throw new PreviewError('Invalid preview grant.');
      }
      const preview = await redeemPreview(environment, body.token);
      for (const [id, session] of sessions) {
        if (session.expires <= Date.now()) sessions.delete(id);
      }
      if (sessions.size >= MAX_SESSIONS) {
        throw new PreviewError('Too many preview sessions. Try again after an existing preview expires.');
      }
      const id = randomBytes(32).toString('base64url');
      const expires = Date.parse(preview.expiresAt);
      sessions.set(hash(id), { token: body.token, expires });
      response.setHeader('Set-Cookie', sessionCookie(environment, id, Math.max(1, Math.floor((expires - Date.now()) / 1000))));
      response.end(JSON.stringify({ path: previewPath(preview.entry) }));
    } catch {
      response.writeHead(401);
      response.end(JSON.stringify({ error: 'Preview expired, revoked or unavailable.' }));
    }
  };
}
