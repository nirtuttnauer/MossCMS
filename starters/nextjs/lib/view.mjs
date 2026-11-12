import { createElement as h } from 'react';
import { pagePath } from '../../../shared/routes.mjs';
import { Markdown } from '../components/Markdown.mjs';
import { entryTitle } from './entries.mjs';
import { markdownField } from './live.mjs';

function formatPublishedAt(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('en', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'UTC',
  }).format(date);
}

function EntryMeta({ page }) {
  return h(
    'p',
    null,
    h('span', null, page.typeKey),
    h('span', null, page.slug),
    page.publishedAt
      ? h('time', { dateTime: page.publishedAt }, formatPublishedAt(page.publishedAt))
      : null,
  );
}

export function EntryIndex({ pages }) {
  return h(
    'main',
    null,
    h('h1', null, 'Published entries'),
    pages.length === 0
      ? h('p', { className: 'status' }, 'No published entries.')
      : h(
          'ul',
          { className: 'entries' },
          pages.map((page) =>
            h(
              'li',
              { key: page.id },
              h(
                'article',
                { 'data-entry-id': page.id },
                h('h2', null, h('a', { href: pagePath(page) }, entryTitle(page))),
                h(EntryMeta, { page }),
              ),
            ),
          ),
        ),
  );
}

export function LivePage({ page, pages }) {
  const links = pages.filter((item) => item.id !== page.id);
  return h(
    'main',
    null,
    links.length
      ? h(
          'nav',
          { 'aria-label': 'Published entries' },
          h(
            'ul',
            { className: 'entries' },
            links.map((item) =>
              h('li', { key: item.id }, h('a', { href: pagePath(item) }, entryTitle(item))),
            ),
          ),
        )
      : null,
    h(
      'article',
      { 'data-entry-id': page.id },
      h('h1', null, entryTitle(page)),
      h(EntryMeta, { page }),
      h(Markdown, { text: markdownField(page), assets: page.resolvedAssets || [] }),
    ),
  );
}

export function loadErrorMessage(error) {
  if (error?.code === 'MISSING_TOKEN') return 'Set MOSS_DELIVERY_TOKEN in the server environment.';
  if (error instanceof TypeError) return 'MossCMS could not be reached.';
  if (error instanceof Error && error.message) return error.message;
  return 'Published entries could not be loaded.';
}

export function LoadError({ error }) {
  return h(
    'main',
    null,
    h('h1', null, 'Published entries'),
    h('p', { className: 'status', role: 'alert' }, loadErrorMessage(error)),
  );
}
