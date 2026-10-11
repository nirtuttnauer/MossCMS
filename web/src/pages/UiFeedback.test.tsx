import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { Assets } from './Assets'
import { Content } from './Content'
import { PublicationQueue } from './PublicationQueue'
import { gql } from '../lib/api'

vi.mock('../lib/api', async importOriginal => ({ ...await importOriginal<typeof import('../lib/api')>(), gql: vi.fn() }))
afterEach(() => { cleanup(); vi.clearAllMocks() })

test('an empty filtered library can clear its search and publishing status', async () => {
  vi.mocked(gql).mockResolvedValue({ entries: { nodes: [], total: 0, endCursor: null, hasNextPage: false }, contentGroups: [] })
  render(<Content types={[]} role="reader" onChanged={vi.fn()} />)
  fireEvent.change(screen.getByLabelText('Search entries'), { target: { value: 'missing' } })
  fireEvent.change(screen.getByLabelText('Publishing status'), { target: { value: 'draft' } })
  await waitFor(() => expect(vi.mocked(gql).mock.calls.some(([, variables]) => variables?.search === 'missing')).toBe(true))
  fireEvent.click(await screen.findByRole('button', { name: 'Clear search and status' }))
  expect((screen.getByLabelText('Search entries') as HTMLInputElement).value).toBe('')
  expect((screen.getByLabelText('Publishing status') as HTMLSelectElement).value).toBe('')
  await waitFor(() => {
    const calls = vi.mocked(gql).mock.calls
    expect(calls[calls.length - 1]?.[1]?.search).toBe('')
  })
  expect(screen.queryByRole('button', { name: 'New entry' })).toBeNull()
})

test('asset loading and request errors do not claim the media library is empty', async () => {
  let reject!: (reason: Error) => void
  vi.mocked(gql).mockImplementation(() => new Promise((_resolve, fail) => { reject = fail }))
  render(<Assets role="reader" onChanged={vi.fn()} />)
  expect(screen.getByRole('status').textContent).toBe('Loading assets…')
  expect(screen.queryByText('A home for your media')).toBeNull()
  reject(new Error('Connection unavailable'))
  expect((await screen.findByRole('alert')).textContent).toBe('Connection unavailable')
  expect(screen.queryByText('A home for your media')).toBeNull()
  expect(screen.queryByRole('button', { name: 'Upload asset' })).toBeNull()
})

test('a failed queue request does not reassure editors that the queue is clear', async () => {
  vi.mocked(gql).mockRejectedValue(new Error('Queue unavailable'))
  render(<PublicationQueue types={[]} role="editor" onChanged={vi.fn()} />)
  expect((await screen.findByRole('alert')).textContent).toBe('Queue unavailable')
  expect(screen.queryByText('Your queue is clear')).toBeNull()
})
