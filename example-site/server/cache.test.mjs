import test from 'node:test';
import assert from 'node:assert/strict';
import { cachedWebsite, invalidateWebsite } from './cache.mjs';

test('cached values are isolated from callers and refresh after five seconds', async t => {
  t.mock.timers.enable({ apis: ['Date'], now: 1000000 });
  let reads = 0;
  const load = async () => ({ pages: [{ title: 'Public' }], revision: ++reads });
  const first = await cachedWebsite(t.name, load);
  first.pages[0].title = 'Preview';
  t.mock.timers.tick(4999);
  assert.deepEqual(await cachedWebsite(t.name, load), { pages: [{ title: 'Public' }], revision: 1 });
  t.mock.timers.tick(1);
  assert.equal((await cachedWebsite(t.name, load)).revision, 2);
  assert.equal(reads, 2);
});

test('concurrent callers share a load but receive separate copies', async t => {
  const deferred = Promise.withResolvers();
  let reads = 0;
  const load = () => { reads++; return deferred.promise; };
  const first = cachedWebsite(t.name, load);
  const second = cachedWebsite(t.name, load);
  assert.equal(reads, 1);
  deferred.resolve({ pages: [] });
  const [a, b] = await Promise.all([first, second]);
  a.pages.push('Preview');
  assert.deepEqual(b.pages, []);
  assert.deepEqual((await cachedWebsite(t.name, load)).pages, []);
});

test('invalidated loads cannot refill the cache or remove a pending replacement', async t => {
  const old = Promise.withResolvers();
  const replacement = Promise.withResolvers();
  const first = cachedWebsite(t.name, () => old.promise);
  invalidateWebsite();
  const second = cachedWebsite(t.name, () => replacement.promise);
  old.resolve({ revision: 1 });
  assert.equal((await first).revision, 1);
  const third = cachedWebsite(t.name, () => assert.fail('Replacement should still be pending.'));
  replacement.resolve({ revision: 2 });
  assert.deepEqual(await Promise.all([second, third]), [{ revision: 2 }, { revision: 2 }]);
  assert.equal((await cachedWebsite(t.name, () => assert.fail('Replacement should be cached.'))).revision, 2);
});

test('a late invalidated load cannot overwrite the replacement', async t => {
  const old = Promise.withResolvers();
  const first = cachedWebsite(t.name, () => old.promise);
  invalidateWebsite();
  await cachedWebsite(t.name, async () => ({ revision: 2 }));
  old.resolve({ revision: 1 });
  await first;
  assert.equal((await cachedWebsite(t.name, () => assert.fail('Replacement should be cached.'))).revision, 2);
});

test('outages can use stale data for ten minutes without extending its lifetime', async t => {
  t.mock.timers.enable({ apis: ['Date'], now: 1000000 });
  await cachedWebsite(t.name, async () => ({ pages: [] }));
  const error = new Error('Delivery unavailable');
  const fail = async () => { throw error; };
  t.mock.timers.tick(599999);
  const stale = await cachedWebsite(t.name, fail);
  assert.equal(stale.stale, true);
  stale.pages.push('Preview');
  assert.deepEqual((await cachedWebsite(t.name, fail)).pages, []);
  t.mock.timers.tick(1);
  await assert.rejects(cachedWebsite(t.name, fail), error);
  assert.deepEqual(await cachedWebsite(t.name, async () => ({ pages: ['Recovered'] })), { pages: ['Recovered'] });
});

test('failed initial loads are not retained and can be retried', async t => {
  await assert.rejects(cachedWebsite(t.name, async () => { throw new Error('Unavailable'); }), /Unavailable/);
  assert.deepEqual(await cachedWebsite(t.name, async () => ({ pages: [] })), { pages: [] });
});

test('the cache evicts its oldest key when it reaches ten entries', async t => {
  let reads = 0;
  const load = async () => ({ revision: ++reads });
  await cachedWebsite(t.name + '0', load);
  for (let i = 1; i <= 10; i++) await cachedWebsite(t.name + i, async () => ({ revision: i }));
  assert.equal((await cachedWebsite(t.name + '0', load)).revision, 2);
});
