import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { Assets } from './Assets'
import { gql, type Asset } from '../lib/api'

vi.mock('../lib/api', async importOriginal => ({ ...await importOriginal<typeof import('../lib/api')>(), gql: vi.fn() }))
afterEach(() => { cleanup(); vi.resetAllMocks(); vi.useRealTimers() })

const page = (name: string) => ({ assetPage: { nodes: [{ id: name, name, mime: 'image/png', size: 1024, url: '/media/example' } as Asset], endCursor: null } })

test('a slow earlier asset search cannot replace newer results or clear their loading state', async () => {
  let oldResult!: (value: ReturnType<typeof page>) => void
  let newResult!: (value: ReturnType<typeof page>) => void
  vi.mocked(gql).mockImplementation((_query, variables) => {
    if (variables?.search === 'old') return new Promise(resolve => { oldResult = resolve })
    if (variables?.search === 'new') return new Promise(resolve => { newResult = resolve })
    return Promise.resolve(page('Initial image'))
  })
  render(<Assets role="reader" onChanged={vi.fn()} />)
  await screen.findByText('Initial image')
  fireEvent.change(screen.getByLabelText('Search assets'), { target: { value: 'old' } })
  await waitFor(() => expect(oldResult).toBeDefined())
  fireEvent.change(screen.getByLabelText('Search assets'), { target: { value: 'new' } })
  await waitFor(() => expect(newResult).toBeDefined())
  await act(async () => oldResult(page('Stale image')))
  expect(screen.queryByText('Stale image')).toBeNull()
  expect(screen.getByRole('region', { name: 'Media library' }).getAttribute('aria-busy')).toBe('true')
  await act(async () => newResult(page('Current image')))
  expect(screen.getByText('Current image')).toBeTruthy()
  expect(screen.getByRole('region', { name: 'Media library' }).getAttribute('aria-busy')).toBe('false')
})

test('rapid search edits issue one request for the final text', async () => {
  vi.mocked(gql).mockResolvedValue(page('Initial image'))
  render(<Assets role="reader" onChanged={vi.fn()} />)
  await screen.findByText('Initial image')
  vi.mocked(gql).mockClear()
  vi.useFakeTimers()
  const input = screen.getByLabelText('Search assets')
  fireEvent.change(input, { target: { value: 'c' } })
  fireEvent.change(input, { target: { value: 'ca' } })
  fireEvent.change(input, { target: { value: 'cat' } })
  expect(gql).not.toHaveBeenCalled()
  await act(async () => { vi.advanceTimersByTime(200) })
  expect(gql).toHaveBeenCalledExactlyOnceWith(expect.any(String), { search: 'cat', imagesOnly: false, after: null })
})

test('a failed asset request can be retried without losing the search', async () => {
  vi.mocked(gql).mockRejectedValueOnce(new Error('Media unavailable')).mockResolvedValueOnce(page('Recovered image'))
  render(<Assets role="reader" onChanged={vi.fn()} />)
  fireEvent.click(await screen.findByRole('button', { name: 'Retry assets' }))
  await screen.findByText('Recovered image')
  expect(screen.queryByRole('alert')).toBeNull()
})
