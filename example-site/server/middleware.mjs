import { eventMiddleware } from './events.mjs';
import { feedMiddleware } from './feeds.mjs';
import { siteMiddleware } from './moss.mjs';
import { pageMiddleware } from './pages.mjs';
import { previewMiddleware } from './preview.mjs';

export function websiteMiddleware(environment, template) {
  // Preview headers must be applied before any content or static response.
  const handlers = [
    previewMiddleware(environment),
    siteMiddleware(environment),
    eventMiddleware(environment),
    feedMiddleware(environment),
    pageMiddleware(environment, template),
  ];
  return (request, response, next) => {
    let index = 0;
    function dispatch() {
      const handler = handlers[index++];
      return handler ? handler(request, response, dispatch) : next();
    }
    return dispatch();
  };
}
