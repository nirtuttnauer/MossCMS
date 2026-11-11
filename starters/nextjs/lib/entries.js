import { createDeliveryClient } from '../../../shared/delivery.mjs';

const publishedQuery = `query PublishedEntries($after: String) {
  entries(first: 100, after: $after) {
    nodes { id typeKey slug publishedAt data }
    endCursor hasNextPage
  }
}`;

export function entryTitle(entry) {
  const title = entry?.data?.title;
  if (typeof title === 'string' && title.trim()) return title.trim();
  if (title && typeof title === 'object' && !Array.isArray(title)) {
    const values = Object.values(title).filter((value) => typeof value === 'string' && value.trim());
    if (values.length) return values.map((value) => value.trim()).join(' / ');
  }
  return entry?.slug ?? '';
}

export async function loadPublishedEntries(environment = process.env) {
  const baseUrl = environment.MOSS_API_URL || 'http://localhost:8001';
  const delivery = createDeliveryClient({
    baseUrl,
    token: environment.MOSS_DELIVERY_TOKEN,
  });
  const entries = [];
  const seen = new Set();
  let after = null;
  for (let page = 0; page < 20; page += 1) {
    const result = await delivery.query(publishedQuery, { after });
    const connection = result?.entries;
    if (!connection || !Array.isArray(connection.nodes) || typeof connection.hasNextPage !== 'boolean') {
      const error = new Error('MossCMS returned an invalid entry page.');
      error.code = 'INVALID_RESPONSE';
      throw error;
    }
    entries.push(...connection.nodes);
    if (!connection.hasNextPage) return entries;
    if (typeof connection.endCursor !== 'string' || !connection.endCursor || seen.has(connection.endCursor)) {
      const error = new Error('MossCMS pagination did not advance.');
      error.code = 'INVALID_CURSOR';
      throw error;
    }
    seen.add(connection.endCursor);
    after = connection.endCursor;
  }
  const error = new Error('Published entries exceed 2,000.');
  error.code = 'PAGE_LIMIT';
  throw error;
}
