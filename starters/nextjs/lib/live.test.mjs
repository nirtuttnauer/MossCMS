import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { Markdown } from '../components/Markdown.mjs';
import { EntryIndex, LivePage } from './view.mjs';
import { isLiveEntry, liveResponse, markdownField, pagesFromEntries, requestPath } from './live.mjs';

const publishedAt = '2026-11-11T18:16:22.067422Z';

function entry(overrides) {
  return {
    id: 'live',
    typeKey: 'article',
    slug: 'starter-note',
    status: 'published',
    publishedAt,
    data: { title: 'Moss starter published note', body: '## Live section\n\nThis **published** sentence is visible.' },
    ...overrides,
  };
}

const hiddenDraft = entry({
  id: 'draft',
  slug: 'starter-draft',
  status: 'draft',
  publishedAt: null,
  data: { title: 'Moss starter hidden draft', body: 'SECRET_DRAFT_BODY' },
});

test('drafts are not routed or rendered', () => {
  const pages = pagesFromEntries([
    entry(),
    hiddenDraft,
    entry({
      id: 'scheduled',
      slug: 'starter-scheduled',
      status: 'scheduled',
      publishedAt,
      data: { title: 'Scheduled later', body: 'SECRET_SCHEDULED_BODY' },
    }),
    entry({
      id: 'overlay',
      slug: 'starter-overlay',
      status: 'draft',
      publishedAt,
      data: { title: 'Draft overlay', body: 'SECRET_OVERLAY_BODY' },
    }),
  ]);
  assert.deepEqual(pages.map((page) => page.slug), ['starter-note']);
  assert.equal(isLiveEntry(hiddenDraft), false);
  assert.equal(liveResponse(pages, '/starter-draft').status, 404);
  assert.equal(liveResponse(pages, '/starter-note').status, 200);
  const index = renderToStaticMarkup(createElement(EntryIndex, { pages }));
  const article = renderToStaticMarkup(createElement(LivePage, { page: pages[0], pages }));
  for (const html of [index, article]) {
    assert.match(html, /Moss starter published note/);
    assert.equal(html.includes('Moss starter hidden draft'), false);
    assert.equal(html.includes('SECRET_DRAFT_BODY'), false);
    assert.equal(html.includes('SECRET_SCHEDULED_BODY'), false);
    assert.equal(html.includes('SECRET_OVERLAY_BODY'), false);
    assert.equal(html.includes('Draft overlay'), false);
  }
  assert.match(article, /<h2>Live section<\/h2>/);
  assert.match(article, /<strong>published<\/strong>/);
  assert.match(index, /href="\/starter-note"/);
});

test('markdown uses the shared URL policy and leaves raw HTML unrendered', () => {
  const html = renderToStaticMarkup(
    createElement(Markdown, {
      text: [
        'Line one',
        'Line two',
        '',
        '[ok](https://example.com)',
        '',
        '[bad](javascript:alert(1))',
        '',
        '<script>alert(1)</script>',
        '',
        '![Cover](asset:image)',
        '',
        '![Skip](asset:file)',
      ].join('\n'),
      assets: [
        { id: 'image', mime: 'image/png', url: 'https://media.example/image' },
        { id: 'file', mime: 'text/plain', url: 'https://media.example/file' },
      ],
    }),
  );
  assert.match(html, /<br\s*\/?>/);
  assert.match(html, /href="https:\/\/example.com"/);
  assert.equal(html.includes('javascript:'), false);
  assert.equal(html.includes('<script'), false);
  assert.match(html, /src="https:\/\/media\.example\/image"/);
  assert.equal(html.includes('https://media.example/file'), false);
  assert.match(html, /Image unavailable/);
});

test('localized markdown bodies stay text', () => {
  assert.equal(markdownField({ body: { en: 'Hello', he: 'שלום' } }), 'Hello\n\nשלום');
  assert.equal(markdownField({ body: { en: '  ', he: 1 } }), '');
  assert.equal(markdownField({}), '');
});

test('example website routes and a plain published slug resolve the same way', () => {
  const pages = pagesFromEntries([
    entry({
      id: 'home',
      typeKey: 'sitePage',
      slug: 'home',
      data: { title: 'Home', kind: 'home', body: 'Welcome' },
    }),
    entry({
      id: 'blog',
      typeKey: 'sitePage',
      slug: 'journal',
      data: { title: 'Journal', kind: 'blog' },
    }),
    entry({
      id: 'post',
      typeKey: 'sitePost',
      slug: 'c',
      data: { title: 'Current', body: 'Live post' },
    }),
    entry({
      id: 'draft-post',
      typeKey: 'sitePost',
      slug: 'secret',
      status: 'draft',
      publishedAt: null,
      data: { title: 'Secret post', body: 'SECRET_DRAFT_BODY' },
    }),
    entry({
      id: 'note',
      typeKey: 'article',
      slug: 'starter-note',
      data: { title: 'Moss starter published note', body: 'Visible' },
    }),
    entry({
      id: 'profile',
      typeKey: 'siteProfile',
      slug: 'profile',
      data: { title: 'Profile', body: 'Not a page' },
    }),
  ]);
  assert.equal(liveResponse(pages, '/').kind, 'page');
  assert.equal(liveResponse(pages, '/').page.id, 'home');
  assert.equal(liveResponse(pages, '/home').status, 308);
  assert.equal(liveResponse(pages, '/home').location, '/');
  assert.equal(liveResponse(pages, '/blog/c').page.id, 'post');
  assert.equal(liveResponse(pages, '/c').status, 308);
  assert.equal(liveResponse(pages, '/c').location, '/blog/c');
  assert.equal(liveResponse(pages, '/blog/secret').status, 404);
  assert.equal(liveResponse(pages, '/starter-note').page.id, 'note');
  assert.equal(liveResponse(pages, '/profile').status, 404);
  const rendered = renderToStaticMarkup(
    createElement(LivePage, { page: liveResponse(pages, '/blog/c').page, pages }),
  );
  assert.match(rendered, /Live post/);
  assert.equal(rendered.includes('SECRET_DRAFT_BODY'), false);
  const redirects = [{ from: '/blog/a', to: '/blog/c', entryId: 'post' }];
  assert.equal(liveResponse(pages, '/blog/a', redirects).status, 308);
  assert.equal(liveResponse(pages, '/blog/a', redirects).location, '/blog/c');
  const reserved = pagesFromEntries([
    entry({
      id: 'other',
      typeKey: 'siteProject',
      slug: 'old',
      data: { title: 'Old project' },
    }),
  ]);
  assert.equal(liveResponse(reserved, '/old', [], ['/old']).status, 404);
  assert.equal(liveResponse(reserved, '/projects/old', [], ['/old']).page.id, 'other');
});

test('encoded slugs round-trip through the shared route helpers', () => {
  const vectors = JSON.parse(readFileSync(new URL('../../../shared/slug-vectors.json', import.meta.url), 'utf8'));
  const route = vectors.cases.find((item) => item.id === 'nextjs-hebrew');
  const hebrew = vectors.cases.find((item) => item.id === 'hebrew-title');
  const pages = pagesFromEntries([
    entry({ id: 'guide', slug: route.slug, data: { title: route.input, body: 'Guide' } }),
    entry({
      id: 'post',
      typeKey: 'sitePost',
      slug: hebrew.slug,
      data: { title: hebrew.input, body: 'Post' },
    }),
  ]);
  assert.equal(requestPath([route.slug]), route.websitePath);
  assert.equal(liveResponse(pages, route.websitePath).page.id, 'guide');
  assert.equal(liveResponse(pages, `/${route.slug}`).page.id, 'guide');
  assert.equal(liveResponse(pages, hebrew.websitePath).page.id, 'post');
  assert.equal(requestPath(undefined), '/');
  assert.equal(liveResponse(pages, '/..%2F..%2Fetc').status, 404);
});
