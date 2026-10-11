import test from 'node:test';
import assert from 'node:assert/strict';
import { createHmac } from 'node:crypto';
import { EventEmitter } from 'node:events';
import { Readable } from 'node:stream';
import { verifyEvent, eventMiddleware } from './events.mjs';
import { cachedWebsite, invalidateWebsite } from './cache.mjs';

const environment = { MOSS_WEBHOOK_SECRET: 'test-secret', SITE_MOSS_WORKSPACE_ID: 'workspace' };
const event = { id: 'event', workspaceId: 'workspace', event: 'published' };

function signedHeaders(body, timestamp = String(Math.floor(Date.now() / 1000))) {
  return {
    'x-moss-event-id': event.id,
    'x-moss-timestamp': timestamp,
    'x-moss-signature': 'sha256=' + createHmac('sha256', environment.MOSS_WEBHOOK_SECRET)
      .update(timestamp + '.').update(body).digest('hex'),
  };
}

function response() {
  const result = new EventEmitter();
  result.headers = {};
  result.messages = [];
  result.setHeader = (name, value) => { result.headers[name] = value; };
  result.writeHead = (status, headers = {}) => { result.status = status; Object.assign(result.headers, headers); };
  result.write = body => result.messages.push(body);
  result.end = () => { result.ended = true; };
  return result;
}

async function deliver(body, headers = signedHeaders(body), method = 'POST', url = '/api/moss-events') {
  const request = Object.assign(Readable.from([body]), { url, method, headers });
  const result = response();
  await eventMiddleware(environment)(request, result, () => { result.delegated = true; });
  return result;
}

test('verified workspace-scoped events invalidate cache and duplicates are safe', async () => {
  const body = JSON.stringify(event);
  assert.equal(verifyEvent(body, signedHeaders(body), environment).id, event.id);
  let reads = 0;
  const load = async () => ({ pages: [], value: ++reads });
  invalidateWebsite();
  const initial = await cachedWebsite('test', load);
  initial.pages.push('preview');
  assert.equal((await cachedWebsite('test', load)).pages.length, 0);
  for (let i = 0; i < 2; i++) {
    assert.equal((await deliver(body)).status, 204);
    await cachedWebsite('test', load);
  }
  assert.equal(reads, 2);
  invalidateWebsite();
  assert.equal((await cachedWebsite('test', async () => { throw new Error(); })).stale, true);
});

test('event verification rejects invalid credentials, signatures, payloads and scope', () => {
  const body = JSON.stringify(event);
  const headers = signedHeaders(body);
  for (const invalid of [
    {},
    { ...headers, 'x-moss-signature': 'sha256=short' },
    { ...headers, 'x-moss-signature': 'sha256=' + '0'.repeat(64) },
    { ...headers, 'x-moss-event-id': 'other' },
    { ...headers, 'x-moss-timestamp': 'invalid' },
  ]) assert.equal(verifyEvent(body, invalid, environment), null);
  assert.equal(verifyEvent(body + ' ', headers, environment), null);
  assert.equal(verifyEvent(body, headers, { ...environment, MOSS_WEBHOOK_SECRET: '' }), null);
  assert.equal(verifyEvent(body, headers, { ...environment, SITE_MOSS_WORKSPACE_ID: '' }), null);
  assert.equal(verifyEvent(body, headers, { ...environment, SITE_MOSS_WORKSPACE_ID: 'other' }), null);
  for (const invalid of [
    'invalid JSON', 'null', '[]',
    JSON.stringify({ ...event, workspaceId: 'other' }),
    JSON.stringify({ ...event, id: 1 }),
    JSON.stringify({ ...event, id: 'x'.repeat(101) }),
    JSON.stringify({ ...event, event: 'draft' }),
  ]) assert.equal(verifyEvent(invalid, signedHeaders(invalid), environment), null);
});

test('event signatures allow five minutes of clock skew in either direction', t => {
  t.mock.timers.enable({ apis: ['Date'], now: 1700000000000 });
  const body = JSON.stringify(event);
  for (const skew of [-301, -300, 0, 300, 301]) {
    const headers = signedHeaders(body, String(Date.now() / 1000 + skew));
    assert.deepEqual(verifyEvent(body, headers, environment), Math.abs(skew) <= 300 ? event : null);
  }
});

test('the receiver enforces byte limits and rejects bad signatures and methods', async () => {
  const base = JSON.stringify({ ...event, id: 'size-limit', padding: '' });
  const body = JSON.stringify({ ...event, id: 'size-limit', padding: 'x'.repeat(8192 - Buffer.byteLength(base)) });
  const headers = { ...signedHeaders(body), 'x-moss-event-id': 'size-limit' };
  assert.equal(Buffer.byteLength(body), 8192);
  assert.equal((await deliver(body, headers)).status, 204);
  assert.equal((await deliver(body + ' ')).status, 400);
  const multibyte = JSON.stringify({ ...event, padding: '😀'.repeat(2100) });
  assert.ok(multibyte.length < 8192);
  assert.equal((await deliver(multibyte)).status, 400);
  assert.equal((await deliver(JSON.stringify(event), {})).status, 403);
  assert.equal((await deliver('', {}, 'GET')).status, 405);
  assert.equal((await deliver('', {}, 'POST', '/api/events')).status, 405);
  assert.equal((await deliver('', {}, 'GET', '/unrelated')).delegated, true);
});

test('the receiver verifies the original bytes across split multibyte chunks', async () => {
  const body = Buffer.from(JSON.stringify({ ...event, id: 'split-bytes', padding: '😀' }));
  const split = body.indexOf(Buffer.from('😀')) + 2;
  const request = Object.assign(Readable.from([body.subarray(0, split), new Uint8Array(body.subarray(split))]), {
    url: '/api/moss-events', method: 'POST',
    headers: { ...signedHeaders(body), 'x-moss-event-id': 'split-bytes' },
  });
  const result = response();
  await eventMiddleware(environment)(request, result, () => assert.fail('Receiver must terminate.'));
  assert.equal(result.status, 204);
  assert.equal(result.headers['Cache-Control'], 'no-store');
});

test('event streams send heartbeats and stop writing after disconnect', async t => {
  t.mock.timers.enable({ apis: ['setInterval'] });
  const stream = await deliver('', {}, 'GET', '/api/events');
  t.after(() => stream.emit('close'));
  assert.equal(stream.status, 200);
  assert.equal(stream.headers['Content-Type'], 'text/event-stream');
  assert.match(stream.messages[0], /^data: \d+\n\n$/);
  t.mock.timers.tick(15000);
  assert.equal(stream.messages[1], ': keepalive\n\n');
  stream.emit('close');
  const count = stream.messages.length;
  t.mock.timers.tick(15000);
  const body = JSON.stringify({ ...event, id: 'after-disconnect' });
  assert.equal((await deliver(body, { ...signedHeaders(body), 'x-moss-event-id': 'after-disconnect' })).status, 204);
  assert.equal(stream.messages.length, count);
});
