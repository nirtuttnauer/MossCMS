import { pagePath, routePage } from '../../../shared/routes.mjs';

const WEBSITE_TYPES = new Set(['sitePage', 'siteProject', 'sitePost', 'siteProfile', 'siteSlide']);

export function isLiveEntry(entry) {
  if (!entry || typeof entry !== 'object') return false;
  if (typeof entry.slug !== 'string' || entry.slug.length === 0) return false;
  if (typeof entry.status === 'string' && entry.status !== 'published') return false;
  if (typeof entry.publishedAt !== 'string' || entry.publishedAt.length === 0) return false;
  return true;
}

function publicEntry(entry) {
  const data = entry.data && typeof entry.data === 'object' && !Array.isArray(entry.data) ? entry.data : {};
  return {
    ...data,
    id: entry.id,
    typeKey: entry.typeKey,
    publishedAt: entry.publishedAt,
    slug: entry.slug,
    status: 'published',
    resolvedAssets: Array.isArray(entry.resolvedAssets) ? entry.resolvedAssets : [],
  };
}

export function pagesFromEntries(entries) {
  const live = (Array.isArray(entries) ? entries : []).filter(isLiveEntry);
  const records = (key) => live.filter((entry) => entry.typeKey === key);
  const pages = records('sitePage').map(publicEntry);
  const projectParent = pages.find((page) => page.kind === 'projects')?.slug ?? 'projects';
  const blogParent = pages.find((page) => page.kind === 'blog')?.slug ?? 'blog';
  const contentEntries = live.filter((entry) => ['sitePage', 'siteProject', 'sitePost'].includes(entry.typeKey));
  const slugCounts = new Map();
  contentEntries.forEach((entry) => slugCounts.set(entry.slug, (slugCounts.get(entry.slug) ?? 0) + 1));
  function childEntry(entry, parent, prefix) {
    return {
      ...publicEntry(entry),
      kind: 'page',
      parentSlug: parent,
      slug: `${prefix}/${entry.slug}`,
      aliases: slugCounts.get(entry.slug) === 1 ? [entry.slug] : [],
    };
  }
  pages.push(...records('siteProject').map((entry) => childEntry(entry, projectParent, 'projects')));
  pages.push(...records('sitePost').map((entry) => childEntry(entry, blogParent, 'blog')));
  const used = new Set(pages.map((page) => page.slug));
  for (const entry of live) {
    if (WEBSITE_TYPES.has(entry.typeKey)) continue;
    if (used.has(entry.slug)) continue;
    const page = publicEntry(entry);
    if (typeof page.kind !== 'string' || !page.kind) page.kind = 'page';
    pages.push(page);
    used.add(page.slug);
  }
  return pages;
}

export function markdownField(page) {
  const value = page?.body;
  if (typeof value === 'string') return value;
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return Object.values(value)
      .filter((item) => typeof item === 'string' && item.trim())
      .join('\n\n');
  }
  return '';
}

export function requestPath(segments) {
  if (!Array.isArray(segments) || segments.length === 0) return '/';
  return `/${segments.map((segment) => encodeURIComponent(segment)).join('/')}`;
}

export function liveResponse(pages, path, redirects = [], reservedPaths = []) {
  const page = routePage(pages, path, redirects, reservedPaths);
  if (!page) {
    return path === '/' ? { kind: 'index', status: 200 } : { kind: 'missing', status: 404 };
  }
  const canonical = pagePath(page);
  if (canonical !== path) return { kind: 'redirect', status: 308, location: canonical, page };
  return { kind: 'page', status: 200, page };
}
