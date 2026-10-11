export function pagePath(page) {
  return page.kind === 'home' || page.slug === 'home'
    ? '/' : '/' + page.slug.split('/').map(encodeURIComponent).join('/');
}

export function routeSlug(path) {
  try {
    return decodeURIComponent(path).replace(/^\/+|\/+$/g, '') || 'home';
  } catch {
    return null;
  }
}

export function routePage(pages, path, redirects = [], reservedPaths = []) {
  const slug = routeSlug(path);
  const historical = redirects.find(redirect =>
    redirect.from.startsWith('/') && !redirect.from.startsWith('//') && routeSlug(redirect.from) === slug &&
    redirect.to.startsWith('/') && !redirect.to.startsWith('//') && !redirect.to.includes('..')
  );
  return pages.find(page => page.slug === slug) ||
    (historical && pages.find(page => page.id === historical.entryId && pagePath(page) === historical.to)) ||
    (!reservedPaths.some(reserved => routeSlug(reserved) === slug) && pages.find(page => page.aliases?.includes(slug))) ||
    (slug === 'home' ? pages.find(page => page.kind === 'home') : undefined);
}
