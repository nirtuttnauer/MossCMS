import test from 'node:test';
import assert from 'node:assert/strict';
import { loadWebsite, websiteFromEntries } from './moss.mjs';

test('website projection preserves section routing, alias collisions, metadata and profile preference', () => {
  const entries = [
    { id: 'projects', typeKey: 'sitePage', slug: 'work', data: { kind: 'projects' } },
    { id: 'blog', typeKey: 'sitePage', slug: 'journal', data: { kind: 'blog' } },
    { id: 'project', typeKey: 'siteProject', slug: 'shared', data: { title: 'Project' } },
    { id: 'post', typeKey: 'sitePost', slug: 'shared', data: { title: 'Post' } },
    { id: 'unique', typeKey: 'sitePost', slug: 'unique', data: { id: 'untrusted', title: 'Unique' }, publishedAt: '2026-01-01T00:00:00Z', resolvedAssets: [] },
    { id: 'alternate', typeKey: 'siteProfile', slug: 'alternate', data: { name: 'Alternate' } },
    { id: 'preferred', typeKey: 'siteProfile', slug: 'profile', data: { name: 'Preferred' } },
    { id: 'slide', typeKey: 'siteSlide', slug: 'unique', data: { enabled: true } },
  ];
  const original = structuredClone(entries);
  const website = websiteFromEntries(entries, 'https://site.example');
  assert.equal(website.profile.name, 'Preferred');
  const project = website.pages.find(page => page.id === 'project');
  const post = website.pages.find(page => page.id === 'post');
  assert.equal(project.slug, 'projects/shared');
  assert.equal(project.parentSlug, 'work');
  assert.deepEqual(project.aliases, []);
  assert.equal(post.slug, 'blog/shared');
  assert.equal(post.parentSlug, 'journal');
  assert.deepEqual(post.aliases, []);
  const unique = website.pages.find(page => page.id === 'unique');
  assert.deepEqual(unique.aliases, ['unique']);
  assert.equal(unique.typeKey, 'sitePost');
  assert.equal(unique.publishedAt, entries[4].publishedAt);
  assert.deepEqual(unique.resolvedAssets, []);
  assert.equal(website.slides[0].id, 'slide');
  assert.deepEqual(entries, original);
  assert.deepEqual(websiteFromEntries([], 'https://site.example'), { siteUrl: 'https://site.example', profile: null, pages: [], slides: [] });
});

test('the loader paginates with server-only credentials and normalizes the public origin', async t => {
  const fetch = t.mock.method(globalThis, 'fetch', async (_url, options) => {
    const { after } = JSON.parse(options.body).variables;
    return { ok: true, json: async () => ({ data: { entries: {
      nodes: after ? [{ id: 'post', typeKey: 'sitePost', slug: 'post', data: { title: 'Post' } }] : [{ id: 'home', typeKey: 'sitePage', slug: 'home', data: { kind: 'home' } }],
      hasNextPage: !after,
      endCursor: after ? null : 'second-page',
    } } }) };
  });
  const website = await loadWebsite({ MOSS_API_URL: 'https://cms.pagination.example/subpath', MOSS_DELIVERY_TOKEN: 'test-only', SITE_PUBLIC_URL: 'https://site.example/subpath' });
  assert.equal(website.siteUrl, 'https://site.example');
  assert.equal(website.pages.length, 2);
  assert.equal(fetch.mock.callCount(), 2);
  for (const { arguments: [url, options] } of fetch.mock.calls) {
    assert.equal(String(url), 'https://cms.pagination.example/delivery/graphql');
    assert.equal(options.headers.Authorization, 'Bearer test-only');
    assert.equal(options.method, 'POST');
  }
  assert.equal(JSON.parse(fetch.mock.calls[1].arguments[1].body).variables.after, 'second-page');
});

test('the loader validates credentials and protocols before making requests', async t => {
  const fetch = t.mock.method(globalThis, 'fetch', () => assert.fail('Invalid configuration must not make requests.'));
  await assert.rejects(loadWebsite({}), /MOSS_DELIVERY_TOKEN is missing/);
  await assert.rejects(loadWebsite({ MOSS_API_URL: 'file:///tmp/cms', MOSS_DELIVERY_TOKEN: 'test' }), /Invalid MossCMS URL/);
  await assert.rejects(loadWebsite({ MOSS_DELIVERY_TOKEN: 'test', SITE_PUBLIC_URL: 'mailto:owner@example.com' }), /Invalid public website URL/);
  assert.equal(fetch.mock.callCount(), 0);
});

test('the loader retains its pagination bound and propagates HTTP and GraphQL errors', async t => {
  const fetch = t.mock.method(globalThis, 'fetch', async () => ({ ok: true, json: async () => ({ data: { entries: { nodes: [], hasNextPage: true, endCursor: 'next' } } }) }));
  await assert.rejects(loadWebsite({ MOSS_API_URL: 'https://cms.limit.example', MOSS_DELIVERY_TOKEN: 'test' }), /2,000-entry limit/);
  assert.equal(fetch.mock.callCount(), 20);
  fetch.mock.mockImplementation(async () => ({ ok: false, status: 401 }));
  await assert.rejects(loadWebsite({ MOSS_API_URL: 'https://cms.http-error.example', MOSS_DELIVERY_TOKEN: 'test' }), /HTTP 401/);
  fetch.mock.mockImplementation(async () => ({ ok: true, json: async () => ({ errors: [{ message: 'Denied' }, { message: 'Out of scope' }] }) }));
  await assert.rejects(loadWebsite({ MOSS_API_URL: 'https://cms.graphql-error.example', MOSS_DELIVERY_TOKEN: 'test' }), /Denied; Out of scope/);
});
