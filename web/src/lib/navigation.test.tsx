import { expect, test } from 'vitest'
import { contentHash, readContentRoute } from './navigation'
import { formatFieldPath } from './api'
test('invalid filters and cursors recover and unknown credential parameters are excluded', () => {
  const route = readContentRoute([], '#content?type=missing&status=invalid&sort=bad&cursor=stale&entry=e1&workspace=w1&token=secret&csrf=secret&preview=secret')
  expect(route).toEqual({ workspace: 'w1', entry: 'e1', type: '', status: '', sort: 'updated_desc', search: '' })
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
