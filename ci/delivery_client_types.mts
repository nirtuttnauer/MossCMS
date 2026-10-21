import { createDeliveryClient, MossDeliveryError, type DeliveryEntry } from '../shared/delivery.mjs';

function typeAssertions() {
  const client = createDeliveryClient({ baseUrl: 'https://cms.example', token: 'fixture-only-token' });
  const pages: AsyncGenerator<DeliveryEntry<{ title: string }>[]> = client.pages<{ title: string }>('article', 20);
  const query: Promise<{ allCmsArticle: Array<{ id: string }> }> = client.query('{allCmsArticle{id}}');
  const error = new MossDeliveryError('Example', 'EXAMPLE', 'fixture-request');
  const code: string = error.code;
  const requestId: string | undefined = error.requestId;
  void [pages, query, code, requestId];

  // @ts-expect-error delivery credentials must be a string
  createDeliveryClient({ baseUrl: 'https://cms.example', token: 123 });
  // @ts-expect-error page size must be numeric
  client.pages('article', '20');
}
void typeAssertions;
