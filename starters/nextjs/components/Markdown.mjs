import { createElement as h } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkBreaks from 'remark-breaks';
import { markdownUrl } from '../../../shared/markdown.mjs';

function MarkdownImage({ src, alt }) {
  if (!src) {
    const label = alt || 'Unavailable image';
    return h('span', { role: 'img', 'aria-label': label }, `[Image unavailable: ${alt || ''}]`);
  }
  return h('img', { src, alt: alt || '', loading: 'lazy' });
}

export function Markdown({ text, assets = [] }) {
  return h(
    'div',
    { className: 'markdown-content' },
    h(ReactMarkdown, {
      skipHtml: true,
      remarkPlugins: [remarkBreaks],
      urlTransform: markdownUrl(assets),
      components: { img: MarkdownImage },
      children: text || '',
    }),
  );
}
