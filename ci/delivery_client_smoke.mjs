import assert from 'node:assert/strict';
import { writeFileSync } from 'node:fs';
import { createDeliveryClient, MossDeliveryError } from '../shared/delivery.mjs';

const delivery = createDeliveryClient({ baseUrl: 'http://app:8001', token: 'fixture-only-benchmark-delivery-token' });
let pages = 0;
for await (const entries of delivery.pages('article', 20)) {
  assert.equal(entries.length, 20);
  assert.ok(entries.every(entry => entry.typeKey === 'article' && entry.publishedAt));
  assert.ok(!JSON.stringify(entries).includes('PRIVATE-BENCHMARK-MARKER'));
  if (++pages === 2) break;
}
assert.equal(pages, 2);
await assert.rejects(delivery.query('{allCmsRestricted{id}}'), error =>
  error instanceof MossDeliveryError && error.code === 'GRAPHQL_VALIDATION' && Boolean(error.requestId));
writeFileSync('/results/delivery-client-checks.json', JSON.stringify({ streamingPages: pages, privateFieldsExcluded: true,
  tokenScopeEnforced: true, structuredErrorAndRequestId: true }, null, 2) + '\n');
