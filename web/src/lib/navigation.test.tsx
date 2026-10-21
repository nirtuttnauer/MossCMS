import { expect, test } from 'vitest'
import { contentHash, readContentRoute } from './navigation'
import { formatFieldPath } from './api'
test('invalid filters and cursors recover and unknown credential parameters are excluded', () => {
  const route = readContentRoute([], '#content?type=missing&status=invalid&sort=bad&cursor=stale&entry=e1&workspace=w1&token=secret&csrf=secret&preview=secret')
  expect(route).toEqual({ workspace: 'w1', entry: 'e1', field: '', seoSnapshot: '', type: '', status: '', sort: 'updated_desc', search: '' })
  expect(contentHash(route)).toBe('#content?workspace=w1&entry=e1')
})
test('legacy hashes remain compatible', () => {
  expect(contentHash(readContentRoute([], '#content'))).toBe('#content')
})
test('structured server paths identify list and localized controls', () => {
  expect(formatFieldPath(['data', 'items', 1, 'title', 'he'])).toBe('data.items[1].title.he')
  expect(formatFieldPath(['slug'])).toBe('slug')
})

test('GraphQL structured errors preserve server metadata and map array paths', async () => {
  const { gql } = await import('./api')
  const { vi } = await import('vitest')
  const request = vi.spyOn(globalThis, 'fetch').mockResolvedValue({ ok: true, json: async () => ({ errors: [{ message: 'Use a valid reference.', extensions: { code: 'VALIDATION', requestId: 'req-1', fieldPath: ['data', 'items', 0, 'target'], reason: 'invalid_reference' } }] }) } as Response)
  try {
    await expect(gql('{entry}')).rejects.toMatchObject({ message: 'Use a valid reference.', code: 'VALIDATION', requestId: 'req-1', fieldPath: 'data.items[0].target', fieldErrors: { 'data.items[0].target': 'Use a valid reference.' }, reason: 'invalid_reference' })
  } finally { request.mockRestore() }
})

test('field sorts are limited to scalar fields on the selected content type', () => {
  const types = [{ id:'t', key:'product', name:'Products', version:1, fields:[{name:'price',type:'number'},{name:'translated',type:'text',localized:true},{name:'nested',type:'object'}] }]
  expect(readContentRoute(types, '#content?type=product&sort=field:price:desc').sort).toBe('field:price:desc')
  for (const sort of ['field:translated:asc','field:nested:asc','field:price:bad','field:missing:asc']) {
    expect(readContentRoute(types, `#content?type=product&sort=${sort}`).sort).toBe('updated_desc')
  }
  expect(readContentRoute(types, '#content?sort=field:price:asc').sort).toBe('updated_desc')
})
