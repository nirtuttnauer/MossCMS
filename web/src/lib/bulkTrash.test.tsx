import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { ApiError, deleteEntryMutation, entryByIdQuery, getContext, gql, setContext, type Entry } from './api'
import { trashEntry } from './bulkTrash'

vi.mock('./api', async original => ({ ...await original<typeof import('./api')>(), gql: vi.fn() }))

const entry: Entry = { id: 'e1', typeKey: 'article', slug: 'one', title: 'One', data: {}, status: 'draft', version: 1, updatedAt: '', isLive: false, hasUnpublishedChanges: false }
beforeEach(() => {
  vi.mocked(gql).mockReset()
  setContext('original-workspace', 'original-csrf')
})
afterEach(() => setContext('', ''))

test('successful deletion uses the input version without reading current status', async () => {
  const context = getContext()
  vi.mocked(gql).mockResolvedValueOnce({ deleteEntry: true })

  expect(await trashEntry(entry)).toEqual({ outcome: 'done' })
  expect(gql).toHaveBeenCalledExactlyOnceWith(deleteEntryMutation, { id: entry.id, version: entry.version }, context)
})

test('retry checks status and uses a fresh version, excluding already trashed entries', async () => {
  const context = { project: 'retry-workspace', csrf: 'retry-csrf' }
  vi.mocked(gql).mockResolvedValueOnce({ entry: { ...entry, status: 'deleted' } })
  expect(await trashEntry(entry, true, context)).toEqual({ outcome: 'done' })
  expect(gql).toHaveBeenCalledExactlyOnceWith(entryByIdQuery, { id: entry.id }, context)

  vi.mocked(gql).mockReset()
    .mockResolvedValueOnce({ entry: { ...entry, version: 9 } })
    .mockResolvedValueOnce({ deleteEntry: true })
  expect(await trashEntry(entry, true, context)).toEqual({ outcome: 'done' })
  expect(gql).toHaveBeenCalledTimes(2)
  expect(gql).toHaveBeenNthCalledWith(1, entryByIdQuery, { id: entry.id }, context)
  expect(gql).toHaveBeenNthCalledWith(2, deleteEntryMutation, { id: entry.id, version: 9 }, context)
})

test('retry refuses to delete when the current entry is missing or cannot be read', async () => {
  vi.mocked(gql).mockResolvedValueOnce({ entry: null })
  expect(await trashEntry(entry, true)).toEqual({
    outcome: 'failed',
    reason: 'Entry unavailable. Check your workspace access before retrying.',
  })
  expect(gql).toHaveBeenCalledExactlyOnceWith(entryByIdQuery, { id: entry.id }, getContext())

  vi.mocked(gql).mockReset().mockRejectedValueOnce(new ApiError('Access refused', 'FORBIDDEN'))
  expect(await trashEntry(entry, true)).toEqual({
    outcome: 'uncertain',
    reason: 'Cannot confirm current status. Access refused (FORBIDDEN)',
  })
  expect(gql).toHaveBeenCalledExactlyOnceWith(entryByIdQuery, { id: entry.id }, getContext())
})

test.each([
  { code: 'CONFLICT', uncertain: false, status: 'deleted', expected: { outcome: 'done' } },
  { code: 'NETWORK', uncertain: false, status: 'deleted', expected: { outcome: 'done' } },
  { code: 'CONFLICT', uncertain: false, status: 'draft', expected: { outcome: 'failed', reason: 'Write failed (CONFLICT)', version: 9 } },
  { code: 'TIMEOUT', uncertain: false, status: 'draft', expected: { outcome: 'failed', reason: 'Write failed (TIMEOUT)', version: 9 } },
  { code: 'REQUEST_FAILED', uncertain: true, status: 'deleted', expected: { outcome: 'done' } },
])('$code with uncertain=$uncertain reconciles a confirmed $status entry without retrying deletion', async ({ code, uncertain, status, expected }) => {
  const context = getContext()
  vi.mocked(gql)
    .mockRejectedValueOnce(new ApiError('Write failed', code, undefined, uncertain))
    .mockResolvedValueOnce({ entry: { ...entry, status, version: 9 } })

  expect(await trashEntry(entry)).toEqual(expected)
  expect(gql).toHaveBeenCalledTimes(2)
  expect(gql).toHaveBeenNthCalledWith(1, deleteEntryMutation, { id: entry.id, version: entry.version }, context)
  expect(gql).toHaveBeenNthCalledWith(2, entryByIdQuery, { id: entry.id }, context)
})

test.each([
  { code: 'NETWORK', readFails: false, outcome: 'uncertain' },
  { code: 'TIMEOUT', readFails: true, outcome: 'uncertain' },
  { code: 'CONFLICT', readFails: false, outcome: 'failed' },
  { code: 'CONFLICT', readFails: true, outcome: 'failed' },
])('$code retains its outcome and input version when reconciliation readFails=$readFails', async ({ code, readFails, outcome }) => {
  vi.mocked(gql).mockRejectedValueOnce(new ApiError('Write failed', code))
  if (readFails) {
    vi.mocked(gql).mockRejectedValueOnce(new ApiError('Read refused', 'FORBIDDEN'))
  } else {
    vi.mocked(gql).mockResolvedValueOnce({ entry: null })
  }

  expect(await trashEntry(entry)).toEqual({ outcome, reason: `Write failed (${code})`, version: entry.version })
  expect(gql).toHaveBeenCalledTimes(2)
  expect(gql).toHaveBeenNthCalledWith(2, entryByIdQuery, { id: entry.id }, getContext())
})

test.each([
  { error: new ApiError('Missing', 'NOT_FOUND'), reason: 'Missing (NOT_FOUND)' },
  { error: new Error('Unexpected failure'), reason: 'Unexpected failure' },
])('ordinary write failure $reason performs no reconciliation read', async ({ error, reason }) => {
  vi.mocked(gql).mockRejectedValueOnce(error)

  expect(await trashEntry(entry)).toEqual({ outcome: 'failed', reason, version: entry.version })
  expect(gql).toHaveBeenCalledExactlyOnceWith(deleteEntryMutation, { id: entry.id, version: entry.version }, getContext())
})

test('failed deletion after a retry read falls back to the freshly read version', async () => {
  vi.mocked(gql)
    .mockResolvedValueOnce({ entry: { ...entry, version: 9 } })
    .mockRejectedValueOnce(new ApiError('Lost', 'NETWORK'))
    .mockRejectedValueOnce(new ApiError('Offline', 'NETWORK'))

  expect(await trashEntry(entry, true)).toEqual({ outcome: 'uncertain', reason: 'Lost (NETWORK)', version: 9 })
  expect(gql).toHaveBeenCalledTimes(3)
  expect(gql).toHaveBeenNthCalledWith(2, deleteEntryMutation, { id: entry.id, version: 9 }, getContext())
  expect(gql).toHaveBeenNthCalledWith(3, entryByIdQuery, { id: entry.id }, getContext())
})

test.each([false, true])('captures the original workspace across awaits when reconcileFirst=%s', async reconcileFirst => {
  const originalContext = getContext()
  let finish!: (value: unknown) => void
  let fail!: (reason: Error) => void
  const pending = new Promise((resolve, reject) => {
    finish = resolve
    fail = reject
  })
  vi.mocked(gql).mockReturnValueOnce(pending)
  if (reconcileFirst) {
    vi.mocked(gql).mockRejectedValueOnce(new ApiError('Lost', 'NETWORK'))
  }
  vi.mocked(gql).mockResolvedValueOnce({ entry: { ...entry, status: 'deleted' } })

  const result = trashEntry(entry, reconcileFirst)
  setContext('different-workspace', 'different-csrf')
  if (reconcileFirst) {
    finish({ entry: { ...entry, version: 9 } })
  } else {
    fail(new ApiError('Lost', 'NETWORK'))
  }

  expect(await result).toEqual({ outcome: 'done' })
  expect(gql).toHaveBeenCalledTimes(reconcileFirst ? 3 : 2)
  for (const call of vi.mocked(gql).mock.calls) {
    expect(call[2]).toEqual(originalContext)
  }
  expect(gql).toHaveBeenNthCalledWith(
    reconcileFirst ? 2 : 1,
    deleteEntryMutation,
    { id: entry.id, version: reconcileFirst ? 9 : entry.version },
    originalContext,
  )
})
