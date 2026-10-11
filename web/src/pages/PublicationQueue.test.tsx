import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { gql, type Entry } from '../lib/api'
import { PublicationQueue } from './PublicationQueue'

vi.mock('../lib/api', async original => ({
  ...await original<typeof import('../lib/api')>(),
  gql: vi.fn(),
}))

const query = 'query($failed:Boolean!,$overdue:Boolean!,$offset:Int!){publicationQueue(failed:$failed,overdue:$overdue,offset:$offset,first:25)}'
const scheduled: Entry = {
  id: 'scheduled-entry', typeKey: 'article', slug: 'scheduled', title: 'Scheduled article', data: {},
  status: 'draft', version: 7, updatedAt: '2026-10-11T12:00:00Z',
  isLive: true, hasUnpublishedChanges: true, scheduledRevision: 4, scheduledAt: '2026-10-12T12:00:00Z',
}
const failed: Entry = {
  ...scheduled, scheduledAt: null,
  scheduleError: { code: 'CAPTURE_FAILED', message: 'Captured revision failed', revision: 4, dueAt: '2026-10-12T12:00:00Z', failedAt: '2026-10-12T12:01:00Z' },
}
const queue = (nodes: Entry[] = [], total = nodes.length) => ({ publicationQueue: { nodes, total } })
const deferred = () => {
  let resolve!: (value: unknown) => void
  let reject!: (reason: Error) => void
  const promise = new Promise((done, fail) => { resolve = done; reject = fail })
  return { promise, resolve, reject }
}
const flush = () => act(async () => {})
const disabled = (name: string) => (screen.getByRole('button', { name }) as HTMLButtonElement).disabled

beforeEach(() => {
  vi.useFakeTimers()
  vi.mocked(gql).mockReset()
  vi.mocked(gql).mockResolvedValue(queue())
})
afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.clearAllMocks()
})

test('loads immediately, polls every fifteen seconds, and stops polling on unmount', async () => {
  const view = render(<PublicationQueue types={[]} role="editor" onChanged={vi.fn()} />)
  expect(screen.getByRole('status').textContent).toBe('Loading publications…')
  await flush()
  expect(vi.mocked(gql).mock.calls).toEqual([[query, { failed: false, overdue: false, offset: 0 }]])
  await act(async () => { await vi.advanceTimersByTimeAsync(14999) })
  expect(gql).toHaveBeenCalledTimes(1)
  await act(async () => { await vi.advanceTimersByTimeAsync(1) })
  expect(gql).toHaveBeenCalledTimes(2)
  view.unmount()
  await act(async () => { await vi.advanceTimersByTimeAsync(30000) })
  expect(gql).toHaveBeenCalledTimes(2)
})

test('pages by twenty-five and resets the offset for each queue filter', async () => {
  vi.mocked(gql).mockResolvedValue(queue([scheduled], 51))
  render(<PublicationQueue types={[]} role="editor" onChanged={vi.fn()} />)
  await flush()
  expect(disabled('Previous')).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: 'Next' }))
  await flush()
  expect(gql).toHaveBeenLastCalledWith(query, { failed: false, overdue: false, offset: 25 })
  fireEvent.click(screen.getByRole('button', { name: 'Next' }))
  await flush()
  expect(gql).toHaveBeenLastCalledWith(query, { failed: false, overdue: false, offset: 50 })
  expect(disabled('Next')).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: 'Previous' }))
  await flush()
  expect(gql).toHaveBeenLastCalledWith(query, { failed: false, overdue: false, offset: 25 })
  fireEvent.change(screen.getByRole('combobox', { name: 'Queue' }), { target: { value: 'failed' } })
  await flush()
  expect(gql).toHaveBeenLastCalledWith(query, { failed: true, overdue: false, offset: 0 })
  expect(disabled('Previous')).toBe(true)
  fireEvent.change(screen.getByRole('combobox', { name: 'Queue' }), { target: { value: 'overdue' } })
  await flush()
  expect(gql).toHaveBeenLastCalledWith(query, { failed: false, overdue: true, offset: 0 })
})

test.each(['result', 'error'] as const)('ignores an old filter %s while the current request remains pending', async outcome => {
  const previous = deferred()
  const current = deferred()
  vi.mocked(gql).mockReturnValueOnce(previous.promise).mockReturnValueOnce(current.promise)
  render(<PublicationQueue types={[]} role="editor" onChanged={vi.fn()} />)
  fireEvent.change(screen.getByRole('combobox', { name: 'Queue' }), { target: { value: 'failed' } })
  await act(async () => {
    if (outcome === 'result') previous.resolve(queue([scheduled]))
    else previous.reject(new Error('Old queue failed'))
  })
  expect(screen.queryByText(scheduled.title)).toBeNull()
  expect(screen.queryByRole('alert')).toBeNull()
  expect(screen.getByRole('status').textContent).toBe('Loading publications…')
  await act(async () => { current.resolve(queue([failed])) })
  expect(screen.getByText(failed.title)).toBeTruthy()
  expect(screen.queryByRole('status')).toBeNull()
})

test.each([
  ['retryPublication', 'Retry captured revision', 'Captured revision queued for retry.'],
  ['cancelSchedule', 'Resolve / discard failed schedule', 'Schedule and failure cleared. Live content preserved.'],
] as const)('%s submits the entry version and only refreshes after success', async (name, label, notice) => {
  const mutation = deferred()
  const onChanged = vi.fn()
  vi.mocked(gql).mockImplementation(async request => request.startsWith('mutation') ? mutation.promise : queue([failed]))
  render(<PublicationQueue types={[]} role="editor" onChanged={onChanged} />)
  await flush()
  fireEvent.click(screen.getByRole('button', { name: label }))
  expect(gql).toHaveBeenLastCalledWith(`mutation($id:ID!,$version:Int!){${name}(id:$id,version:$version){id}}`, { id: failed.id, version: 7 })
  expect(disabled('Retry captured revision')).toBe(true)
  expect(disabled('Resolve / discard failed schedule')).toBe(true)
  expect(onChanged).not.toHaveBeenCalled()
  expect(gql).toHaveBeenCalledTimes(2)
  await act(async () => { mutation.resolve({ [name]: { id: failed.id } }) })
  expect(screen.getByRole('status').textContent).toBe(notice)
  expect(onChanged).toHaveBeenCalledTimes(1)
  expect(gql).toHaveBeenLastCalledWith(query, { failed: false, overdue: false, offset: 0 })
  expect(disabled('Retry captured revision')).toBe(false)
  expect(disabled('Resolve / discard failed schedule')).toBe(false)
})

test('a failed cancellation releases busy controls and can be retried without a premature refresh', async () => {
  const onChanged = vi.fn()
  vi.mocked(gql).mockResolvedValue(queue([scheduled]))
  render(<PublicationQueue types={[]} role="editor" onChanged={onChanged} />)
  await flush()
  vi.mocked(gql).mockRejectedValueOnce(new Error('Schedule changed elsewhere'))
  fireEvent.click(screen.getByRole('button', { name: 'Cancel schedule' }))
  await flush()
  expect(screen.getByRole('alert').textContent).toBe('Schedule changed elsewhere')
  expect(disabled('Cancel schedule')).toBe(false)
  expect(onChanged).not.toHaveBeenCalled()
  expect(gql).toHaveBeenCalledTimes(2)
  vi.mocked(gql).mockResolvedValueOnce({ cancelSchedule: { id: scheduled.id } })
  fireEvent.click(screen.getByRole('button', { name: 'Cancel schedule' }))
  await flush()
  expect(screen.queryByRole('alert')).toBeNull()
  expect(onChanged).toHaveBeenCalledTimes(1)
  expect(gql).toHaveBeenCalledTimes(4)
})

test('readers see publication details and view controls without scheduling actions', async () => {
  vi.mocked(gql).mockResolvedValue(queue([failed]))
  render(<PublicationQueue types={[]} role="reader" onChanged={vi.fn()} />)
  await flush()
  expect(screen.getByRole('button', { name: 'View' })).toBeTruthy()
  expect(screen.getByText(/article · captured revision 4/)).toBeTruthy()
  expect(screen.getByText(/CAPTURE_FAILED: Captured revision failed/)).toBeTruthy()
  expect(screen.queryByRole('button', { name: 'Retry captured revision' })).toBeNull()
  expect(screen.queryByRole('button', { name: 'Resolve \/ discard failed schedule' })).toBeNull()
  expect(screen.queryByRole('button', { name: 'Edit \/ replace schedule' })).toBeNull()
})
