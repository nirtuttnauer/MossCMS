import { pagePath } from '../../shared/routes.mjs';

const entities = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
export const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, character => entities[character]);

export function metadata(website, page, environment = {}) {
  const canonical = new URL(pagePath(page), website.siteUrl).href;
  const domain = new URL(website.siteUrl).hostname;
  const title = (page.kind === 'home' ? website.profile?.name : page.title) || 'Example website';
  const description = page.description || website.profile?.headline || 'A example website.';
  let image;
  if (environment.SITE_SOCIAL_IMAGE) {
    try {
      const url = new URL(environment.SITE_SOCIAL_IMAGE, website.siteUrl);
      if (url.protocol === 'https:' && !url.search && !url.hash && !url.username && !url.password) image = url.href;
    } catch { /* Invalid optional social images are omitted. */ }
  }
  return { canonical, title: `${title} — ${domain}`, description, image, preview: Boolean(website.preview) };
}

export function renderHtml(template, website, page, environment = {}) {
  const meta = metadata(website, page, environment);
  const escape = escapeHtml;
  const clean = template
    .replace(/<title>[\s\S]*?<\/title>/gi, '')
    .replace(/<meta\b[^>]*(?:name="(?:description|robots|twitter:[^"]+)"|property="og:[^"]+")[^>]*>/gi, '')
    .replace(/<link\b[^>]*rel="canonical"[^>]*>/gi, '');
  const head = [
    `<title>${escape(meta.title)}</title>`,
    `<meta name="description" content="${escape(meta.description)}">`,
    `<link rel="canonical" href="${escape(meta.canonical)}">`,
    `<meta property="og:type" content="${page.parentSlug ? 'article' : 'website'}">`,
    `<meta property="og:site_name" content="${escape(website.profile?.name || 'Example website')}">`,
    `<meta property="og:title" content="${escape(meta.title)}">`,
    `<meta property="og:description" content="${escape(meta.description)}">`,
    `<meta property="og:url" content="${escape(meta.canonical)}">`,
    `<meta name="twitter:card" content="${meta.image ? 'summary_large_image' : 'summary'}">`,
    meta.image ? `<meta property="og:image" content="${escape(meta.image)}"><meta name="twitter:image" content="${escape(meta.image)}">` : '',
    meta.preview ? '<meta name="robots" content="noindex,nofollow">' : '',
  ].join('');
  return clean.replace('</head>', head + '</head>');
}
