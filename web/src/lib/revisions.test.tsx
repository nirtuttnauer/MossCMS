import { expect, test } from 'vitest'
import { buildRevisionDiffs } from './revisions'
const snapshot = (data: Record<string, unknown>) => ({ slug: 'page', title: 'Page', data })
test('empty translations are additions and removals distinct from absent values', () => {
  const fields = [{ name: 'title', label: 'Title', type: 'text', localized: true }]
  const added = buildRevisionDiffs(fields, snapshot({ title: { en: 'Hello' } }), snapshot({ title: { en: 'Hello', he: '' } }))
  expect(added.find(row => row.key === 'title.he')?.status).toBe('added')
  const removed = buildRevisionDiffs(fields, snapshot({ title: { he: '' } }), snapshot({ title: {} }))
  expect(removed.find(row => row.key === 'title.he')?.status).toBe('removed')
})
test('an optional object presence change is visible even with no populated child fields', () => {
  const fields = [{ name: 'meta', label: 'Metadata', type: 'object', fields: [{ name: 'caption', type: 'text' }] }]
  const rows = buildRevisionDiffs(fields, snapshot({ meta: null }), snapshot({ meta: {} }))
  expect(rows.some(row => row.status === 'added' && row.label === 'Metadata presence')).toBe(true)
})
