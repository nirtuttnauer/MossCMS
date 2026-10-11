import { describe, expect, it } from 'vitest'
import { buildRevisionDiffs, revisionValueIds } from './revisions'
import type { Field } from './api'

const snapshot = (data: Record<string, unknown>) => ({ slug: 'article', title: 'Article', data })

describe('revisionValueIds', () => {
  const row = (type: string, leftVal: unknown, rightVal: unknown) => ({
    key: type, label: type, type, leftVal, rightVal, status: 'changed' as const,
  })

  it.each(['asset', 'reference'] as const)('keeps first-seen left then right order and deduplicates %s IDs', type => {
    expect(revisionValueIds([
      row(type, 'second', 'first'),
      row(type, 'first', 'third'),
      row(type, 'second', 'fourth'),
    ], type)).toBe('second,first,third,fourth')
  })

  it('filters by type and includes only nonempty strings without trimming or parsing them', () => {
    const rows = [
      row('text', 'ignored-text', 'ignored-right'),
      row('asset', '', null),
      row('asset', undefined, 0),
      row('asset', false, true),
      row('asset', [], { id: 'ignored-object' }),
      row('asset', ' ', 'a,b'),
      row('reference', 'reference-only', 'a,b'),
    ]
    expect(revisionValueIds(rows, 'asset')).toBe(' ,a,b')
    expect(revisionValueIds(rows, 'reference')).toBe('reference-only,a,b')
    expect(revisionValueIds([], 'asset')).toBe('')
  })
})

describe('buildRevisionDiffs', () => {
  it('orders nested schema fields before removed children and unions locales in snapshot order', () => {
    const fields: Field[] = [{ name: 'details', label: 'Details', type: 'object', fields: [
      { name: 'body', label: 'Body', type: 'markdown', localized: true },
      { name: 'summary', type: 'text' },
    ] }]
    const left = snapshot({ details: { old: 'legacy', summary: 'same', body: { he: 'ישן', en: 'same' } } })
    const right = snapshot({ details: { body: { en: 'same', he: 'חדש', fr: 'bonjour' }, summary: 'same', extra: 42 } })

    const rows = buildRevisionDiffs(fields, left, right)

    expect(rows.slice(2).map(({ key, label, type, status }) => ({ key, label, type, status }))).toEqual([
      { key: 'details.body.he', label: 'Details › Body (he)', type: 'markdown', status: 'changed' },
      { key: 'details.body.en', label: 'Details › Body (en)', type: 'markdown', status: 'unchanged' },
      { key: 'details.body.fr', label: 'Details › Body (fr)', type: 'markdown', status: 'added' },
      { key: 'details.summary', label: 'Details › summary', type: 'text', status: 'unchanged' },
      { key: 'details.old', label: 'Details › old (removed schema field)', type: 'unknown', status: 'removed' },
      { key: 'details.extra', label: 'Details › extra (removed schema field)', type: 'unknown', status: 'added' },
    ])
    expect(rows[2]).toMatchObject({ leftVal: 'ישן', rightVal: 'חדש' })
    expect(rows[4]).toMatchObject({ leftVal: undefined, rightVal: 'bonjour' })
  })

  it('compares list positions, recurses into localized object items, and marks missing items', () => {
    const fields: Field[] = [{ name: 'steps', label: 'Steps', type: 'list', item: {
      name: '', type: 'object', fields: [{ name: 'title', label: 'Title', type: 'text', localized: true }],
    } }]
    const a = { title: { en: 'A' } }, b = { title: { en: 'B' } }
    const rows = buildRevisionDiffs(fields, snapshot({ steps: [a, b, a] }), snapshot({ steps: [b, a] })).slice(2)

    expect(rows).toEqual([
      { key: 'steps[0].title.en', label: 'Steps › Item 1 › Title (en)', type: 'text', leftVal: 'A', rightVal: 'B', status: 'changed' },
      { key: 'steps[1].title.en', label: 'Steps › Item 2 › Title (en)', type: 'text', leftVal: 'B', rightVal: 'A', status: 'changed' },
      { key: 'steps[2].title.en', label: 'Steps › Item 3 › Title (en)', type: 'text', leftVal: 'A', rightVal: undefined, status: 'removed' },
    ])
    const added = buildRevisionDiffs([{ name: 'tags', type: 'list' }], snapshot({}), snapshot({ tags: ['new'] }))[2]
    expect(added).toEqual({ key: 'tags[0]', label: 'tags › Item 1', type: 'text', leftVal: undefined, rightVal: 'new', status: 'added' })
  })

  it('appends removed top-level schema fields in snapshot order and keeps unknown objects intact', () => {
    const legacy = { nested: 'old' }
    const rows = buildRevisionDiffs([{ name: 'current', type: 'text' }],
      snapshot({ old: legacy, current: 'same', shared: 'before' }),
      snapshot({ current: 'same', newUnknown: 'new', shared: 'after' }),
    )

    expect(rows.map(row => row.key)).toEqual(['_slug', '_title', 'current', 'old', 'shared', 'newUnknown'])
    expect(rows.slice(3)).toEqual([
      { key: 'old', label: 'old (removed schema field)', type: 'unknown', leftVal: legacy, rightVal: undefined, status: 'removed' },
      { key: 'shared', label: 'shared (removed schema field)', type: 'unknown', leftVal: 'before', rightVal: 'after', status: 'changed' },
      { key: 'newUnknown', label: 'newUnknown (removed schema field)', type: 'unknown', leftVal: undefined, rightVal: 'new', status: 'added' },
    ])
  })

  it.each([
    [undefined, null, 'unchanged'], [null, '', 'added'], ['', undefined, 'removed'],
    [undefined, 'value', 'added'], [null, false, 'added'], ['value', null, 'removed'],
    [0, undefined, 'removed'], ['', 'value', 'changed'], ['value', '', 'changed'],
    [false, 0, 'changed'], [0, 0, 'unchanged'],
    [{ a: 1, b: 2 }, { a: 1, b: 2 }, 'unchanged'],
    [{ a: 1, b: 2 }, { b: 2, a: 1 }, 'changed'],
    [['A', 'B'], ['B', 'A'], 'changed'],
  ])('preserves scalar equality and empty statuses for %j → %j', (left, right, status) => {
    const row = buildRevisionDiffs([{ name: 'value', type: 'unknown' }], snapshot({ value: left }), snapshot({ value: right }))[2]
    expect(row).toMatchObject({ leftVal: left, rightVal: right, status })
  })

  it('keeps rows for empty object, localized, and list values without inventing child rows', () => {
    const fields: Field[] = [
      { name: 'object', type: 'object', fields: [{ name: 'child', type: 'text' }] },
      { name: 'localized', type: 'text', localized: true },
      { name: 'list', type: 'list' },
    ]
    const rows = buildRevisionDiffs(fields,
      snapshot({ object: null, localized: {}, list: [] }),
      snapshot({ object: undefined, localized: {}, list: [] }),
    ).slice(2)
    expect(rows.map(({ key, status }) => ({ key, status }))).toEqual([
      { key: 'object', status: 'unchanged' },
      { key: 'localized', status: 'unchanged' },
      { key: 'list', status: 'unchanged' },
    ])
  })

  it('shows empty translation additions and removals while unchanged empty translations stay unchanged', () => {
    const fields: Field[] = [{ name: 'title', type: 'text', localized: true }]
    const rows = buildRevisionDiffs(fields,
      snapshot({ title: { en: '', he: '' } }),
      snapshot({ title: { en: '', ar: '' } }),
    ).slice(2)
    expect(rows.map(({ key, status }) => ({ key, status }))).toEqual([
      { key: 'title.en', status: 'unchanged' },
      { key: 'title.he', status: 'removed' },
      { key: 'title.ar', status: 'added' },
    ])
  })

  it.each([
    [null, {}, 'added'], [{}, null, 'removed'],
  ])('shows optional object presence when its empty children cannot convey %s → %s', (left, right, status) => {
    const rows = buildRevisionDiffs([{ name: 'meta', type: 'object', fields: [{ name: 'caption', type: 'text' }] }],
      snapshot({ meta: left }), snapshot({ meta: right }),
    ).slice(2)
    expect(rows.map(({ key, status }) => ({ key, status }))).toEqual([
      { key: 'meta._presence', status },
      { key: 'meta.caption', status: 'unchanged' },
    ])
  })

  it.each([
    ['', 'value', 'added'], ['value', '', 'removed'], ['before', 'after', 'changed'], ['', '', 'unchanged'],
  ])('starts with slug and title rows using metadata statuses for %j → %j', (left, right, status) => {
    expect(buildRevisionDiffs([], { slug: left, title: left, data: {} }, { slug: right, title: right, data: {} })).toEqual([
      { key: '_slug', label: 'Slug', type: 'slug', leftVal: left, rightVal: right, status },
      { key: '_title', label: 'Title', type: 'text', leftVal: left, rightVal: right, status },
    ])
  })
})
