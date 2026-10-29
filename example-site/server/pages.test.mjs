import test from 'node:test';import assert from 'node:assert/strict';
import {pageMiddleware} from './pages.mjs';import {routePage,pagePath} from '../../shared/routes.mjs';
import { routeSlug } from '../../shared/routes.mjs';
const pages=[{slug:'home',kind:'home'},{slug:'blog/post',aliases:['post']}];
test('stable paths and unique legacy aliases resolve',()=>{assert.equal(pagePath(pages[1]),'/blog/post');assert.equal(routePage(pages,'/post'),pages[1]);assert.equal(routePage(pages,'/blog%2Fpost'),pages[1]);assert.equal(routePage(pages,'/unknown'),undefined)});
test('server returns actual public 404s and canonical redirects',async()=>{
 const original=globalThis.fetch;globalThis.fetch=async()=>({ok:true,json:async()=>({data:{entries:{nodes:pages.map((p,i)=>({id:String(i),typeKey:'sitePage',slug:p.slug,data:p})),hasNextPage:false}}})});
 try{for(const [path,status]of [['/',200],['/home',308],['/draft',404]]){const response={status:200,setHeader(){},writeHead(status){this.status=status},end(){}};await pageMiddleware({MOSS_DELIVERY_TOKEN:'test'},()=>'<html>page</html>')({url:path,method:'GET',headers:{}},response,()=>{});assert.equal(response.status,status)}}finally{globalThis.fetch=original}
});

test('route parsing handles encoded slugs and malformed escapes without changing precedence', () => {
  assert.equal(routeSlug('/'), 'home');
  assert.equal(routeSlug('/blog/%D7%A9%D7%9C%D7%95%D7%9D/'), 'blog/שלום');
  assert.equal(routeSlug('/%broken'), null);
  assert.equal(pagePath({ slug: 'blog/שלום' }), '/blog/%D7%A9%D7%9C%D7%95%D7%9D');
  const actual = { slug: 'post' };
  assert.equal(routePage([{ slug: 'blog/post', aliases: ['post'] }, actual], '/post'), actual);
});

test('HEAD avoids rendering and unsupported or static requests delegate without loading content', async t => {
  const next = t.mock.fn();
  const render = t.mock.fn(() => '<html>Home</html>');
  const fetch = t.mock.method(globalThis, 'fetch', async () => ({
    ok: true,
    json: async () => ({ data: { entries: { nodes: [{ id: 'home', typeKey: 'sitePage', slug: 'home', data: { kind: 'home' } }], hasNextPage: false } } }),
  }));
  const middleware = pageMiddleware({ MOSS_DELIVERY_TOKEN: 'head-test' }, render);
  for (const [url, method] of [['/assets/site.js', 'GET'], ['/src/main.tsx', 'GET'], ['/', 'POST']]) {
    await middleware({ url, method, headers: {} }, { setHeader() {}, writeHead() {}, end() {} }, next);
  }
  assert.equal(next.mock.callCount(), 3);
  assert.equal(fetch.mock.callCount(), 0);
  const result = { headers: {}, setHeader(name, value) { this.headers[name] = value; }, writeHead(status) { this.status = status; }, end(body) { this.body = body; } };
  await middleware({ url: '/', method: 'HEAD', headers: {} }, result, next);
  assert.equal(result.status, 200);
  assert.equal(result.body, '');
  assert.equal(result.headers['Cache-Control'], 'no-store');
  assert.equal(render.mock.callCount(), 0);
});

test('historical paths redirect straight to the current live canonical route', async t => {
  t.mock.method(globalThis, 'fetch', async () => ({
    ok: true,
    json: async () => ({ data: {
      entries: { nodes: [{ id: 'post', typeKey: 'sitePost', slug: 'c', data: { title: 'Current' } }], hasNextPage: false },
      websiteRedirects: [
        { from: '/blog/a', to: '/blog/c', entryId: 'post' },
        { from: '/blog/b', to: '/blog/c', entryId: 'post' },
        { from: '/blog/private', to: '/blog/draft', entryId: 'missing' },
        { from: '/blog/external', to: '//outside.example', entryId: 'post' },
      ],
    } }),
  }));
  const middleware = pageMiddleware({ MOSS_DELIVERY_TOKEN: 'historical-route-test' }, () => '<html>Current</html>');
  for (const [path, expected] of [['/blog/a', 308], ['/blog/b', 308], ['/blog/c', 200], ['/blog/private', 404], ['/blog/external', 404]]) {
    const response = { headers: {}, setHeader(name, value) { this.headers[name] = value; }, writeHead(status, headers = {}) { this.status = status; Object.assign(this.headers, headers); }, end() {} };
    await middleware({ url: path, method: 'GET', headers: {} }, response, () => {});
    assert.equal(response.status, expected);
    if (expected === 308) assert.equal(response.headers.Location, '/blog/c');
  }
});

test('recorded history takes precedence over an incidental legacy alias', () => {
  const target = { id: 'original', slug: 'blog/current' };
  const incidental = { id: 'other', slug: 'projects/old', aliases: ['old'] };
  const redirects = [{ from: '/old', to: '/blog/current', entryId: 'original' }];
  assert.equal(routePage([incidental, target], '/old', redirects), target);
  assert.equal(routePage([incidental], '/old', redirects), incidental);
});

test('hebrew nextjs route resolves from the raw slug and the percent-encoded URL', async () => {
  const { readFileSync } = await import('node:fs');
  const vectors = JSON.parse(readFileSync(new URL('../../shared/slug-vectors.json', import.meta.url), 'utf8'));
  const route = vectors.cases.find(item => item.id === 'nextjs-hebrew');
  const hebrew = vectors.cases.find(item => item.id === 'hebrew-title');
  const page = { slug: route.slug };
  const post = { slug: `blog/${hebrew.slug}` };
  assert.equal(pagePath(page), route.websitePath);
  assert.equal(routePage([page], route.websitePath), page);
  assert.equal(routePage([page], `/${route.slug}`), page);
  assert.equal(pagePath(post), hebrew.websitePath);
  assert.equal(routePage([post], hebrew.websitePath), post);
  assert.equal(routePage([post], `/blog/${hebrew.slug}`), post);
  assert.equal(routePage([page], '/..%2F..%2Fetc'), undefined);
  assert.equal(routePage([post], '/%2F'), undefined);
});

test('unpublished reserved URLs return unavailable instead of another entry legacy alias', () => {
  const incidental = { id: 'other', slug: 'projects/old', aliases: ['old'] };
  assert.equal(routePage([incidental], '/old', [], ['/old']), undefined);
  assert.equal(routePage([incidental], '/projects/old', [], ['/old']), incidental);
});
