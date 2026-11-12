import test from 'node:test';
import assert from 'node:assert/strict';
import { runInNewContext } from 'node:vm';
import {Readable} from 'node:stream';
import {previewMiddleware,loadPreview,applyPreview,PreviewError} from './preview.mjs';
const environment={MOSS_API_URL:'https://cms.example',MOSS_DELIVERY_TOKEN:'test-only',SITE_PUBLIC_URL:'https://site.example'};
function response(){return {headers:{},status:200,setHeader(k,v){this.headers[k.toLowerCase()]=v},writeHead(status,headers={}){this.status=status;for(const [k,v]of Object.entries(headers))this.setHeader(k,v)},end(body=''){this.body=body}}}
function request(url,method='GET',headers={},body=''){const r=Readable.from(Array.isArray(body)?body:[body]);r.url=url;r.method=method;r.headers=headers;return r}
test('preview session is HttpOnly, scoped, revalidated, and revocable',async()=>{
  const original=globalThis.fetch;
  const grant={entry:{id:'draft',typeKey:'sitePost',slug:'draft',data:{title:'Draft'}},revision:2,expiresAt:new Date(Date.now()+600000).toISOString()};
  globalThis.fetch=async()=>({ok:true,json:async()=>grant});
  try {
    const r=response();await previewMiddleware(environment)(request('/api/preview','POST',{'content-type':'application/json',origin:'https://site.example'},JSON.stringify({token:'temporary-preview-grant'})),r,()=>{});
    assert.equal(r.status,200);assert.match(r.headers['set-cookie'],/HttpOnly; SameSite=Lax/);assert.match(r.headers['set-cookie'],/Secure/);
    assert.equal(r.headers['cache-control'],'no-store');assert.ok(!r.body.includes('temporary-preview-grant'));
    const cookie=r.headers['set-cookie'].split(';')[0];
    const preview=await loadPreview(request('/api/site','GET',{cookie}),environment);
    const website=applyPreview({pages:[],slides:[],profile:null},preview);
    assert.equal(website.pages[0].slug,'blog/draft');assert.equal(website.preview.revision,2);
    assert.equal(await loadPreview(request('/api/site'),environment),null);
    globalThis.fetch=async()=>({ok:false});
    await assert.rejects(()=>loadPreview(request('/api/site','GET',{cookie}),environment),PreviewError);
  } finally {globalThis.fetch=original}
});
test('bootstrap strips fragment credentials before redemption and blocks cross-origin POST',async()=>{
  const middleware=previewMiddleware(environment),r=response();await middleware(request('/preview'),r,()=>{});
  assert.match(r.body,/history.replaceState/);assert.match(r.headers['x-robots-tag'],/noindex/);assert.match(r.headers['content-security-policy'],/default-src 'none'/);assert.match(r.headers['content-security-policy'],/frame-ancestors https:\/\/cms\.example/);
  const blocked=response();await middleware(request('/api/preview','POST',{origin:'https://evil.example'}),blocked,()=>{});assert.equal(blocked.status,403);
});

test('the generated bootstrap removes credentials before sending the grant and redirects after redemption', async () => {
  const result = response();
  await previewMiddleware(environment)(request('/preview'), result, () => assert.fail('Bootstrap must terminate.'));
  const [, nonce, script] = result.body.match(/<script nonce="([^"]+)">([\s\S]*?)<\/script>/);
  assert.ok(result.headers['content-security-policy'].includes(`nonce-${nonce}`));
  const calls = [];
  await runInNewContext(script, {
    URLSearchParams,
    location: { hash: '#grant=temporary-preview-grant', replace: path => calls.push(['redirect', path]) },
    history: { replaceState: (_state, _title, path) => calls.push(['strip', path]) },
    fetch: async (url, options) => {
      calls.push(['fetch', url, JSON.parse(options.body).token]);
      return { ok: true, json: async () => ({ path: '/blog/draft' }) };
    },
    document: { querySelector: () => assert.fail('Successful bootstrap must not display an error.') },
  });
  assert.deepEqual(calls, [
    ['strip', '/preview'],
    ['fetch', '/api/preview', 'temporary-preview-grant'],
    ['redirect', '/blog/draft'],
  ]);
});

test('preview sessions expire locally and exit clears the cookie', async t => {
  t.mock.timers.enable({ apis: ['Date'], now: 2000000000000 });
  const grant = {
    entry: { id: 'expiry', typeKey: 'sitePage', slug: 'draft', data: {} },
    revision: 1,
    expiresAt: new Date(Date.now() + 1000).toISOString(),
  };
  const fetch = t.mock.method(globalThis, 'fetch', async () => ({ ok: true, json: async () => grant }));
  const middleware = previewMiddleware(environment);
  const created = response();
  await middleware(request('/api/preview', 'POST', { 'content-type': 'application/json' }, JSON.stringify({ token: 'temporary-preview-grant' })), created, () => {});
  assert.equal(created.status, 200);
  const cookie = created.headers['set-cookie'].split(';')[0];
  assert.match(created.headers['set-cookie'], /Max-Age=1;/);
  assert.deepEqual(await loadPreview(request('/api/site', 'GET', { cookie }), environment), grant);
  assert.equal(fetch.mock.callCount(), 2);
  t.mock.timers.tick(1000);
  await assert.rejects(loadPreview(request('/api/site', 'GET', { cookie }), environment), PreviewError);
  assert.equal(fetch.mock.callCount(), 2);
  const exited = response();
  await middleware(request('/api/preview/exit', 'POST', { cookie }), exited, () => {});
  assert.match(exited.headers['set-cookie'], /moss_preview=;.*Max-Age=0;/);
});

test('preview request validation rejects invalid bodies before redemption and retains the byte limit', async t => {
  const grant = { entry: { typeKey: 'sitePage', slug: 'draft' }, expiresAt: new Date(Date.now() + 60000).toISOString() };
  const fetch = t.mock.method(globalThis, 'fetch', async () => ({ ok: true, json: async () => grant }));
  const middleware = previewMiddleware(environment);
  for (const body of ['{', 'null', '{}', JSON.stringify({ token: 'short' }), JSON.stringify({ token: 'x'.repeat(101) }), JSON.stringify({ token: '😀'.repeat(600) })]) {
    const result = response();
    await middleware(request('/api/preview', 'POST', { 'content-type': 'application/json' }, body), result, () => {});
    assert.equal(result.status, 401);
    assert.equal(result.headers['cache-control'], 'no-store');
  }
  assert.equal(fetch.mock.callCount(), 0);
  const base = JSON.stringify({ token: 'temporary-preview-grant', padding: '' });
  const body = JSON.stringify({ token: 'temporary-preview-grant', padding: 'x'.repeat(2048 - Buffer.byteLength(base)) });
  const accepted = response();
  await middleware(request('/api/preview', 'POST', { 'content-type': 'application/json' }, [body.slice(0, 1024), body.slice(1024)]), accepted, () => {});
  assert.equal(accepted.status, 200);
  const oversized = response();
  await middleware(request('/api/preview', 'POST', { 'content-type': 'application/json' }, [body.slice(0, 1024), body.slice(1024), ' ']), oversized, () => {});
  assert.equal(oversized.status, 401);
  assert.deepEqual(JSON.parse(oversized.body), { error: 'Preview expired, revoked or unavailable.' });
  assert.equal(oversized.headers['cache-control'], 'no-store');
  assert.equal(oversized.headers['set-cookie'], undefined);
  assert.equal(fetch.mock.callCount(), 1);
  const wrongType = response();
  await middleware(request('/api/preview', 'POST', { 'content-type': 'text/plain' }, body), wrongType, () => {});
  assert.equal(wrongType.status, 415);
  const wrongMethod = response();
  await middleware(request('/api/preview', 'GET'), wrongMethod, () => {});
  assert.equal(wrongMethod.status, 405);
  assert.equal(wrongMethod.headers.allow, 'POST');
});

test('redemption rejects expired, invalid-date and unsupported-type grants', async t => {
  t.mock.timers.enable({ apis: ['Date'], now: 2000000000000 });
  const { redeemPreview } = await import('./preview.mjs');
  const fetch = t.mock.method(globalThis, 'fetch');
  for (const grant of [
    { entry: { typeKey: 'sitePage' }, expiresAt: new Date(Date.now()).toISOString() },
    { entry: { typeKey: 'sitePage' }, expiresAt: 'invalid' },
    { entry: { typeKey: 'article' }, expiresAt: new Date(Date.now() + 60000).toISOString() },
  ]) {
    fetch.mock.mockImplementation(async () => ({ ok: true, json: async () => grant }));
    await assert.rejects(redeemPreview(environment, 'temporary-preview-grant'), PreviewError);
  }
});
