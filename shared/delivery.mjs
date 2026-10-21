/** Server-side delivery queries and streaming pagination; never bundle a privileged token into a browser. */
export class MossDeliveryError extends Error {
  constructor(message, code = 'DELIVERY_ERROR', requestId = undefined) {
    super(message);
    this.name = 'MossDeliveryError';
    this.code = code;
    this.requestId = requestId;
  }
}

const pageQuery = `query DeliveryPage($typeKey: String!, $first: Int!, $after: String) {
  entries(typeKey: $typeKey, first: $first, after: $after) {
    nodes { id typeKey slug publishedAt data resolvedAssets { id mime url width height variants } }
    endCursor hasNextPage
  }
}`;

export function createDeliveryClient({ baseUrl, token }) {
  if (!token) throw new MossDeliveryError('MOSS_DELIVERY_TOKEN is missing. Run scripts/setup_moss.py.', 'MISSING_TOKEN');
  let endpoint;
  try {
    endpoint = new URL('/delivery/graphql', baseUrl);
  } catch {
    throw new MossDeliveryError('Invalid MossCMS URL.', 'INVALID_URL');
  }
  if (!['http:', 'https:'].includes(endpoint.protocol) || endpoint.username || endpoint.password) {
    throw new MossDeliveryError('Invalid MossCMS URL.', 'INVALID_URL');
  }

  async function query(document, variables = {}) {
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ query: document, variables }),
      signal: AbortSignal.timeout(10000),
      cache: 'no-store',
    });
    const requestId = response.headers?.get('X-Request-ID') ?? undefined;
    if (!response.ok) throw new MossDeliveryError(`MossCMS returned HTTP ${response.status}.`, `HTTP_${response.status}`, requestId);
    let result;
    try {
      result = await response.json();
    } catch {
      throw new MossDeliveryError('MossCMS returned invalid JSON.', 'INVALID_RESPONSE', requestId);
    }
    if (result?.errors != null && (!Array.isArray(result.errors) || result.errors.some(error =>
      !error || typeof error.message !== 'string' || (error.extensions?.code != null && typeof error.extensions.code !== 'string')))) {
      throw new MossDeliveryError('MossCMS returned invalid delivery errors.', 'INVALID_RESPONSE', requestId);
    }
    if (result?.errors?.length) {
      const error = result.errors[0];
      throw new MossDeliveryError(result.errors.map(item => item.message).join('; '),
        error.extensions?.code ?? 'GRAPHQL_ERROR', error.extensions?.requestId ?? requestId);
    }
    if (!result?.data || typeof result.data !== 'object' || Array.isArray(result.data)) {
      throw new MossDeliveryError('MossCMS returned no delivery data.', 'INVALID_RESPONSE', requestId);
    }
    return result.data;
  }

  async function* pages(typeKey, first = 100) {
    if (!typeKey || !Number.isInteger(first) || first < 1 || first > 100) {
      throw new MossDeliveryError('Use a content type and page size of 1–100.', 'INVALID_PAGE');
    }
    const seen = new Set();
    let after = null;
    while (true) {
      const data = await query(pageQuery, { typeKey, first, after });
      const page = data.entries;
      if (!page || !Array.isArray(page.nodes) || typeof page.hasNextPage !== 'boolean') {
        throw new MossDeliveryError('MossCMS returned an invalid entry page.', 'INVALID_RESPONSE');
      }
      if (page.hasNextPage) {
        if (typeof page.endCursor !== 'string' || !page.endCursor || seen.has(page.endCursor)) {
          throw new MossDeliveryError('MossCMS pagination did not advance.', 'INVALID_CURSOR');
        }
        seen.add(page.endCursor);
      }
      yield page.nodes;
      if (!page.hasNextPage) return;
      after = page.endCursor;
    }
  }
  return { query, pages };
}
