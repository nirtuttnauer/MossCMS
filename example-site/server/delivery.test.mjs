import test from 'node:test';
import assert from 'node:assert/strict';
import { createDeliveryClient, MossDeliveryError } from '../../shared/delivery.mjs';

const options = { baseUrl: 'https://cms.example', token: 'fixture-only-token' };

test('streaming pagination has no hidden 2,000-entry limit and supports early exit', async t => {
  let calls = 0;
  t.mock.method(globalThis, 'fetch', async (url, config) => {
    assert.equal(String(url), 'https://cms.example/delivery/graphql');
    assert.equal(config.headers.Authorization, 'Bearer fixture-only-token');
    const { after, typeKey } = JSON.parse(config.body).variables;
    assert.equal(typeKey, 'article');
    const index = after ? Number(after) : 0;
    calls += 1;
    return Response.json({ data: { entries: {
      nodes: Array.from({ length: 100 }, (_, n) => ({ id: `${index}-${n}` })),
      hasNextPage: index < 24, endCursor: String(index + 1),
    } } });
  });
  const delivery = createDeliveryClient(options);
  let count = 0;
  for await (const page of delivery.pages('article')) count += page.length;
  assert.equal(count, 2500);
  assert.equal(calls, 25);
  for await (const page of delivery.pages('article')) {
    assert.equal(page.length, 100);
    break;
  }
  assert.equal(calls, 26);
});

test('missing and repeated cursors fail instead of looping forever', async t => {
  const fetch = t.mock.method(globalThis, 'fetch', async () => Response.json({ data: { entries: {
    nodes: [], hasNextPage: true, endCursor: 'same',
  } } }));
  const collect = async () => { for await (const page of createDeliveryClient(options).pages('article')) void page; };
  await assert.rejects(collect, error => error.code === 'INVALID_CURSOR');
  assert.equal(fetch.mock.callCount(), 2);
  fetch.mock.mockImplementation(async () => Response.json({ data: { entries: { nodes: [], hasNextPage: true } } }));
  await assert.rejects(collect, error => error.code === 'INVALID_CURSOR');
});

test('errors retain codes and request IDs without exposing credentials or invalid response bodies', async t => {
  const fetch = t.mock.method(globalThis, 'fetch', async () => new Response('upstream body', {
    status: 503, headers: { 'X-Request-ID': 'http-request' },
  }));
  const delivery = createDeliveryClient(options);
  await assert.rejects(delivery.query('{entries{total}}'), error => {
    assert.ok(error instanceof MossDeliveryError);
    assert.equal(error.code, 'HTTP_503');
    assert.equal(error.requestId, 'http-request');
    assert.ok(!error.message.includes(options.token));
    assert.ok(!error.message.includes('upstream body'));
    return true;
  });
  fetch.mock.mockImplementation(async () => Response.json({ errors: [{ message: 'Denied', extensions: {
    code: 'FORBIDDEN', requestId: 'graphql-request',
  } }] }));
  await assert.rejects(delivery.query('{}'), error => error.code === 'FORBIDDEN' && error.requestId === 'graphql-request');
  fetch.mock.mockImplementation(async () => new Response('private-invalid-json'));
  await assert.rejects(delivery.query('{}'), error => error.code === 'INVALID_RESPONSE' && !error.message.includes('private-invalid-json'));
  for (const result of [{ errors: 'invalid' }, { errors: [null] }, { data: [] }, { data: null }]) {
    fetch.mock.mockImplementation(async () => Response.json(result));
    await assert.rejects(delivery.query('{}'), error => error.code === 'INVALID_RESPONSE');
  }
});

test('invalid configuration and page bounds reject before sending a request', async t => {
  t.mock.method(globalThis, 'fetch', () => assert.fail('Unexpected request'));
  assert.throws(() => createDeliveryClient({ ...options, token: '' }), /missing/);
  for (const baseUrl of ['file:///tmp/cms', 'invalid', 'https://user:password@cms.example']) {
    assert.throws(() => createDeliveryClient({ ...options, baseUrl }), /Invalid MossCMS URL/);
  }
  for (const size of [0, 101, 1.5]) {
    await assert.rejects(async () => {
      for await (const page of createDeliveryClient(options).pages('article', size)) void page;
    }, error => error.code === 'INVALID_PAGE');
  }
});
