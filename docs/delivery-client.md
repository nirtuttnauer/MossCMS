# Typed delivery client

The dependency-free [delivery client](../shared/delivery.mjs) supports server-side GraphQL queries, structured errors, and streaming pagination. [TypeScript declarations](../shared/delivery.d.mts) describe public entries and asset metadata. This is the first CMP-03 integration slice; REST delivery, a Next.js starter, automatic schema-derived type generation, and independent developer trials remain planned.

Use Node.js 22 or newer, copy both client files into your server project or import them from this checkout, and keep the delivery token in the server environment. The example website now uses this client for requests while retaining its own cache, preview handling, and 2,000-entry bulk-load guard. The streaming client has no total-entry cap and stops fetching when the caller breaks iteration; individual pages remain limited to 100 entries.

## Query generated fields

```ts
import { createDeliveryClient, MossDeliveryError } from './delivery.mjs';

const token = process.env.MOSS_DELIVERY_TOKEN;
if (!token) throw new Error('Set MOSS_DELIVERY_TOKEN on the server.');
const cms = createDeliveryClient({
  baseUrl: process.env.MOSS_API_URL ?? 'http://localhost:8001',
  token,
});

type ArticleQuery = {
  allCmsArticle: Array<{ id: string; slug: string; title: string | null; body: string | null }>;
};

try {
  const data = await cms.query<ArticleQuery>(`{
    allCmsArticle(first: 20) { id slug title body(locale: "en") }
  }`);
  console.log(data.allCmsArticle.map(article => article.slug));
} catch (error) {
  if (error instanceof MossDeliveryError) {
    console.error({ code: error.code, requestId: error.requestId });
  }
  throw error;
}
```

The Article fields must exist in your workspace's schema and token scope. These result types describe that explicit query; generic TypeScript arguments are not runtime validators. Inspect the generated schema in the API explorer and update query/result types after schema changes. Automatically generating these types is a later part of CMP-03.

## Process larger collections a page at a time

```ts
type ArticleData = {
  title?: string | null;
  body?: string | Record<string, string> | null;
};

for await (const entries of cms.pages<ArticleData>('article', 100)) {
  for (const entry of entries) {
    // Render or index this page on the server rather than accumulating the whole library.
    console.log(entry.slug, entry.data.title);
  }
}
```

`pages()` returns arrays of public entries with ID, type key, slug, publication time, public JSON data, and resolved image assets. Field-level locale maps in generic `data` remain maps; use generated field queries to select a locale. Assets include signed original/variant URLs that expire after 15 minutes. Refetch delivery content when refreshing expired links and keep website caches shorter than the asset-link lifetime.

Empty/malformed pages and missing or repeated cursors fail explicitly rather than loop forever. Transport requests time out after 10 seconds and do not retry automatically. HTTP/GraphQL failures expose a code and request ID; malformed response bodies are not included in client errors. `fetch` uses `cache: 'no-store'`; application caching and publication invalidation remain explicit frontend responsibilities. See the [webhook contract](webhooks.md) and existing [example-site server cache](../example-site/server/cache.mjs).

The client remains read-only through the delivery endpoint: the server enforces token expiry/scope, published snapshots, workspace boundaries, and private-field exclusion. Browser components should consume responses from your own server rather than receive its delivery credentials.
