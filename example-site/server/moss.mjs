import { cachedWebsite } from './cache.mjs';
import { applyPreview, loadPreview, PreviewError } from './preview.mjs';
const query = `query WebsiteEntries($after: String) {
  websiteRedirects
  websiteReservedPaths
  entries(first: 100, after: $after) {
    nodes { id typeKey slug publishedAt data resolvedAssets { id mime url width height variants } } endCursor hasNextPage
  }
}`;

export function loadWebsite(environment) {
  const key = [environment.MOSS_API_URL, environment.MOSS_DELIVERY_TOKEN, environment.SITE_PUBLIC_URL].join('|');
  return cachedWebsite(key, () => fetchWebsite(environment));
}
async function fetchWebsite(environment) {
  const { MOSS_API_URL = 'http://localhost:8001', MOSS_DELIVERY_TOKEN } = environment;
  if (!MOSS_DELIVERY_TOKEN) throw new Error('MOSS_DELIVERY_TOKEN is missing. Run scripts/setup_moss.py.');
  const endpoint = new URL('/delivery/graphql', MOSS_API_URL);
  if (!['http:', 'https:'].includes(endpoint.protocol)) throw new Error('Invalid MossCMS URL.');
  const publicUrl = new URL(environment.SITE_PUBLIC_URL ?? 'http://localhost:5174');
  if (!['http:', 'https:'].includes(publicUrl.protocol)) throw new Error('Invalid public website URL.');
  const entries = [];
  let redirects = [];
  let reservedPaths = [];
  let after = null;
  for (let page = 0; page < 20; page++) {
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${MOSS_DELIVERY_TOKEN}` },
      body: JSON.stringify({ query, variables: { after } }),
      signal: AbortSignal.timeout(10000),
    });
    if (!response.ok) throw new Error(`MossCMS returned HTTP ${response.status}.`);
    const result = await response.json();
    if (result.errors?.length) throw new Error(result.errors.map(error => error.message).join('; '));
    if (page === 0) {
      redirects = result.data.websiteRedirects ?? [];
      reservedPaths = result.data.websiteReservedPaths ?? [];
    }
    entries.push(...result.data.entries.nodes);
    if (!result.data.entries.hasNextPage) break;
    if (page === 19) throw new Error('Website exceeds the 2,000-entry limit.');
    after = result.data.entries.endCursor;
  }
  return websiteFromEntries(entries, publicUrl.origin, redirects, reservedPaths);
}

export function websiteFromEntries(entries, siteUrl, redirects = [], reservedPaths = []) {
  const records = key => entries.filter(entry => entry.typeKey === key);
  const publicEntry = entry => ({
    ...entry.data,
    id: entry.id,
    typeKey: entry.typeKey,
    publishedAt: entry.publishedAt,
    slug: entry.slug,
    resolvedAssets: entry.resolvedAssets,
  });
  const pages = records('sitePage').map(publicEntry);
  const projectParent = pages.find(page => page.kind === 'projects')?.slug ?? 'projects';
  const blogParent = pages.find(page => page.kind === 'blog')?.slug ?? 'blog';
  const contentEntries = entries.filter(entry => ['sitePage', 'siteProject', 'sitePost'].includes(entry.typeKey));
  const slugCounts = new Map();
  contentEntries.forEach(entry => slugCounts.set(entry.slug, (slugCounts.get(entry.slug) ?? 0) + 1));
  function childEntry(entry, parent, prefix) {
    return {
      ...publicEntry(entry),
      kind: 'page',
      parentSlug: parent,
      slug: `${prefix}/${entry.slug}`,
      aliases: slugCounts.get(entry.slug) === 1 ? [entry.slug] : [],
    };
  }
  pages.push(...records('siteProject').map(entry => childEntry(entry, projectParent, 'projects')));
  pages.push(...records('sitePost').map(entry => childEntry(entry, blogParent, 'blog')));
  const profiles = records('siteProfile');
  const profile = profiles.find(entry => entry.slug === 'profile') ?? profiles[0];
  return {
    siteUrl,
    ...(redirects.length ? { redirects } : {}),
    ...(reservedPaths.length ? { reservedPaths } : {}),
    profile: profile ? publicEntry(profile) : null,
    pages,
    slides: records('siteSlide').map(publicEntry),
  };
}

export function siteMiddleware(environment) {
  return async (request, response, next) => {
    if (request.url?.split('?')[0] !== '/api/site') return next();
    response.setHeader('Content-Type', 'application/json; charset=utf-8');
    response.setHeader('Cache-Control', 'no-store');
    response.setHeader('X-Content-Type-Options', 'nosniff');
    if (request.method !== 'GET') {
      response.writeHead(405, { Allow: 'GET' });
      response.end(JSON.stringify({ error: 'Method not allowed.' }));
      return;
    }
    try {
      const preview = await loadPreview(request, environment);
      const website = await loadWebsite(environment);
      response.end(JSON.stringify(preview ? applyPreview(website, preview) : website));
    } catch (error) {
      console.error('Website content could not be loaded:', error.message);
      response.writeHead(error instanceof PreviewError ? 401 : 502);
      response.end(JSON.stringify({ error: 'Website content is temporarily unavailable.' }));
    }
  };
}
