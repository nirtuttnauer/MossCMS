import test from 'node:test';import assert from 'node:assert/strict';import {sitemap,rss} from './feeds.mjs';
test('public feeds escape XML, use publication time and canonical stable routes',()=>{
 const website={siteUrl:'https://example.com',profile:{name:'Example & Co'},pages:[{id:'one',typeKey:'sitePost',slug:'blog/one',title:'<Post>',description:'A & B',publishedAt:'2026-01-01T00:00:00Z'},{id:'two',typeKey:'siteProject',slug:'projects/two',title:'Project'}]};
 assert.match(sitemap(website),/https:\/\/example\.com\/blog\/one/);assert.match(sitemap(website),/2026-01-01T00:00:00.000Z/);
 const feed=rss(website);assert.match(feed,/&lt;Post&gt;/);assert.match(feed,/A &amp; B/);assert.match(feed,/Thu, 01 Jan 2026/);assert.ok(!feed.includes('projects/two'));assert.match(feed,/<guid isPermaLink="false">moss:one/);
});

test('feeds omit invalid dates and XML control characters, sort posts and cap RSS at 100', () => {
  const pages = Array.from({ length: 105 }, (_, i) => ({
    id: String(i), typeKey: 'sitePost', slug: `blog/post-${i}`, title: `Post ${i}\u0001`,
    publishedAt: new Date(Date.UTC(2026, 0, 1, 0, i)).toISOString(),
  }));
  pages.unshift({ id: 'invalid', typeKey: 'sitePost', slug: 'blog/invalid', title: 'Invalid', publishedAt: 'invalid' });
  const website = { siteUrl: 'https://site.example', pages };
  const feed = rss(website);
  assert.equal((feed.match(/<item>/g) || []).length, 100);
  assert.ok(feed.indexOf('moss:104') < feed.indexOf('moss:103'));
  assert.ok(!feed.includes('moss:invalid'));
  assert.ok(!feed.includes('\u0001'));
  assert.equal(pages[0].id, 'invalid');
  const map = sitemap(website);
  assert.ok(!map.includes('Invalid Date'));
  assert.equal((map.match(/<lastmod>/g) || []).length, 105);
  assert.ok(map.includes('/blog/invalid'));
});
