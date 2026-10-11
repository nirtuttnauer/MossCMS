import type { ContentType } from './api'

const statuses = ['', 'draft', 'published', 'scheduled', 'deleted']
const sorts = ['updated_desc', 'updated_asc', 'title_asc', 'title_desc']
export function readContentRoute(types?: ContentType[], hash = location.hash) {
  const source = new URLSearchParams(hash.split('?')[1] || '')
  const type = source.get('type') || ''
  return {
    workspace: source.get('workspace') || '',
    entry: source.get('entry') || '',
    type: !types || types.some(item => item.key === type) ? type : '',
    status: statuses.includes(source.get('status') || '') ? source.get('status') || '' : '',
    search: (source.get('search') || '').slice(0, 500),
    sort: sorts.includes(source.get('sort') || '') ? source.get('sort') || 'updated_desc' : 'updated_desc',
  }
}
export function contentHash(route: ReturnType<typeof readContentRoute>) {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(route)) {
    if (value && !(key === 'sort' && value === 'updated_desc')) params.set(key, value)
  }
  return `#content${params.size ? `?${params.toString()}` : ''}`
}
export function setContentRoute(route: ReturnType<typeof readContentRoute>, push = false) {
  const hash = contentHash(route)
  if (location.hash === hash) return
  if (push) history.pushState(null, '', hash)
  else history.replaceState(null, '', hash)
  window.dispatchEvent(new Event('moss:locationchange'))
}
