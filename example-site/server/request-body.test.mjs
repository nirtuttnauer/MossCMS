import test from 'node:test';
import assert from 'node:assert/strict';
import { readBody } from './request-body.mjs';

test('empty bodies return an empty Buffer', async () => {
  assert.deepEqual(await readBody([], 0), Buffer.alloc(0));
});

test('the exact byte limit accepts strings, buffers and byte arrays across chunks', async () => {
  const emoji = Buffer.from('😀');
  const chunks = ['é', emoji.subarray(0, 2), new Uint8Array(emoji.subarray(2)), Buffer.from('!')];
  assert.deepEqual(await readBody(chunks, 7), Buffer.from('é😀!'));
});

test('one byte over the limit rejects both single and multiple chunks', async () => {
  for (const chunks of [[Buffer.from('abcd')], ['ab', new Uint8Array([99, 100])], ['é', 'é']]) {
    await assert.rejects(readBody(chunks, 3), error => error.constructor === Error && error.message === 'Too large');
  }
});

test('request stream errors propagate unchanged', async () => {
  const failure = new Error('Connection interrupted');
  async function* request() {
    yield Buffer.from('a');
    throw failure;
  }
  await assert.rejects(readBody(request(), 10), error => error === failure);
});

test('overflow stops consumption and closes the request iterator', async () => {
  let consumed = 0;
  let closed = false;
  async function* request() {
    try {
      for (const chunk of ['ab', 'cd', 'ef']) {
        consumed++;
        yield chunk;
      }
    } finally {
      closed = true;
    }
  }
  await assert.rejects(readBody(request(), 3), /Too large/);
  assert.equal(consumed, 2);
  assert.equal(closed, true);
});
