export function pagePath(page) {return page.kind==='home' || page.slug==='home' ? '/' : '/'+page.slug.split('/').map(encodeURIComponent).join('/')}
export function routeSlug(path) {try {return decodeURIComponent(path).replace(/^\/+|\/+$/g,'') || 'home'}catch{return null}}
export function routePage(pages,path) {const slug=routeSlug(path);return pages.find(p=>p.slug===slug) || pages.find(p=>p.aliases?.includes(slug)) || (slug==='home'?pages.find(p=>p.kind==='home'):undefined)}
