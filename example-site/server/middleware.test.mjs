import test from 'node:test';
import assert from 'node:assert/strict';
import { websiteMiddleware } from './middleware.mjs';

const environment = {
  MOSS_API_URL: 'https://cms.pipeline.example',
  MOSS_DELIVERY_TOKEN: 'pipeline-test',
  SITE_PUBLIC_URL: 'https://site.example',
};

function response() {
  return {
    status: 200,
    headers: {},
    setHeader(name, value) { this.headers[name.toLowerCase()] = value; },
    writeHead(status, headers = {}) {
      this.status = status;
      for (const [name, value] of Object.entries(headers)) this.setHeader(name, value);
    },
    end(body) { this.body = body; },
  };
}

test('the shared pipeline intercepts site JSON and feeds before page rendering', async t => {
  t.mock.method(globalThis, 'fetch', async () => ({
    ok: true,
    json: async () => ({ data: { entries: {
      nodes: [{ id: 'home', typeKey: 'sitePage', slug: 'home', data: { kind: 'home', title: 'Home' } }],
      hasNextPage: false,
    } } }),
  }));
  const render = t.mock.fn(() => '<html>Home</html>');
  const next = t.mock.fn();
  const middleware = websiteMiddleware(environment, render);
  for (const path of ['/api/site', '/sitemap.xml', '/rss.xml', '/']) {
    const result = response();
    await middleware({ url: path, method: 'GET', headers: {} }, result, next);
    assert.equal(result.status, 200);
    assert.equal(result.headers['cache-control'], 'no-store');
    if (path === '/api/site') assert.equal(JSON.parse(result.body).pages[0].id, 'home');
    else if (path.endsWith('.xml')) assert.match(result.body, /^<\?xml/);
    else assert.equal(result.body, '<html>Home</html>');
  }
  assert.equal(render.mock.callCount(), 1);
  assert.equal(next.mock.callCount(), 0);
});

test('preview headers reach delegated static and Vite responses', async t => {
  const next = t.mock.fn();
  const middleware = websiteMiddleware(environment);
  for (const path of ['/assets/site.js', '/@vite/client', '/src/main.tsx', '/api/unhandled']) {
    const result = response();
    await middleware({ url: path, method: 'GET', headers: { cookie: 'moss_preview=opaque-session' } }, result, next);
    assert.equal(result.headers['cache-control'], 'no-store');
    assert.equal(result.headers['x-robots-tag'], 'noindex, nofollow');
    assert.equal(result.headers['referrer-policy'], 'no-referrer');
  }
  assert.equal(next.mock.callCount(), 4);
});

test('the preview bootstrap terminates the pipeline before delivery or rendering', async t => {
  const fetch = t.mock.method(globalThis, 'fetch', () => assert.fail('Bootstrap must not fetch published content.'));
  const render = t.mock.fn();
  const next = t.mock.fn();
  const result = response();
  await websiteMiddleware(environment, render)({ url: '/preview', method: 'GET', headers: {} }, result, next);
  assert.match(result.headers['content-security-policy'], /default-src 'none'/);
  assert.match(result.body, /history.replaceState/);
  assert.equal(result.headers['cache-control'], 'no-store');
  assert.equal(fetch.mock.callCount(), 0);
  assert.equal(render.mock.callCount(), 0);
  assert.equal(next.mock.callCount(), 0);
});
