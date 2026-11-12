import { createDeliveryClient } from '../../../shared/delivery.mjs';
import { pagesFromEntries } from './live.mjs';

const websiteQuery = `query WebsiteEntries($after: String) {
  websiteRedirects
  websiteReservedPaths
  entries(first: 100, after: $after) {
    nodes { id typeKey slug status publishedAt data resolvedAssets { id mime url } }
    endCursor hasNextPage
  }
}`;

export function entryTitle(entry) {
  const title = entry?.data?.title ?? entry?.title;
  if (typeof title === 'string' && title.trim()) return title.trim();
  if (title && typeof title === 'object' && !Array.isArray(title)) {
    const values = Object.values(title).filter((value) => typeof value === 'string' && value.trim());
    if (values.length) return values.map((value) => value.trim()).join(' / ');
  }
  return entry?.slug ?? '';
}

function invalid(message, code) {
  const error = new Error(message);
  error.code = code;
  return error;
}

export async function loadWebsite(environment = process.env) {
  const baseUrl = environment.MOSS_API_URL || 'http://localhost:8001';
  const delivery = createDeliveryClient({
    baseUrl,
    token: environment.MOSS_DELIVERY_TOKEN,
  });
  const entries = [];
  const seen = new Set();
  let redirects = [];
  let reservedPaths = [];
  let after = null;
  for (let page = 0; page < 20; page += 1) {
    const result = await delivery.query(websiteQuery, { after });
    if (page === 0) {
      if (!Array.isArray(result?.websiteRedirects) || !Array.isArray(result?.websiteReservedPaths)) {
        throw invalid('MossCMS returned an invalid website route list.', 'INVALID_RESPONSE');
      }
      redirects = result.websiteRedirects;
      reservedPaths = result.websiteReservedPaths;
    }
    const connection = result?.entries;
    if (!connection || !Array.isArray(connection.nodes) || typeof connection.hasNextPage !== 'boolean') {
      throw invalid('MossCMS returned an invalid entry page.', 'INVALID_RESPONSE');
    }
    entries.push(...connection.nodes);
    if (!connection.hasNextPage) {
      return { pages: pagesFromEntries(entries), redirects, reservedPaths };
    }
    if (typeof connection.endCursor !== 'string' || !connection.endCursor || seen.has(connection.endCursor)) {
      throw invalid('MossCMS pagination did not advance.', 'INVALID_CURSOR');
    }
    seen.add(connection.endCursor);
    after = connection.endCursor;
  }
  throw invalid('Published entries exceed 2,000.', 'PAGE_LIMIT');
}
