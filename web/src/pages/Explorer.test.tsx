import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { ApiError, gql, message, type ContentType } from '../lib/api'
import { Explorer } from './Explorer'

vi.mock('../lib/api', async importOriginal => ({
  ...await importOriginal<typeof import('../lib/api')>(),
  gql: vi.fn(),
}))

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn())
})

afterEach(() => {
  cleanup()
  vi.resetAllMocks()
  vi.unstubAllGlobals()
})

test('editorial queries pass parsed variables to gql and format the result', async () => {
  const result = { entries: { nodes: [{ id: 'entry-1' }], total: 1 } }
  vi.mocked(gql).mockResolvedValue(result)
  render(<Explorer types={[]} />)
  expect(screen.getByRole('status').textContent).toBe('Run a query to see its result.')

  const query = 'query($first: Int!) { entries(first: $first) { total } }'
  fireEvent.change(screen.getByLabelText('Query'), { target: { value: query } })
  fireEvent.change(screen.getByLabelText('Variables'), { target: { value: '{"first":2,"filter":{"status":"draft"}}' } })
  fireEvent.click(screen.getByRole('button', { name: 'Run query' }))

  await waitFor(() => expect(screen.getByRole('status').textContent).toBe(JSON.stringify(result, null, 2)))
  expect(gql).toHaveBeenCalledExactlyOnceWith(query, { first: 2, filter: { status: 'draft' } })
  expect(fetch).not.toHaveBeenCalled()
  expect((screen.getByRole('button', { name: 'Run query' }) as HTMLButtonElement).disabled).toBe(false)
})

test('delivery queries send the token, query and parsed variables to the delivery endpoint', async () => {
  const result = { data: { allCmsPost: [{ id: 'published-1' }] } }
  const readJson = vi.fn().mockResolvedValue(result)
  vi.mocked(fetch).mockResolvedValue({ json: readJson } as unknown as Response)
  render(<Explorer types={[]} />)

  const query = 'query($limit: Int!) { allCmsPost(first: $limit) { id } }'
  fireEvent.change(screen.getByLabelText('Query'), { target: { value: query } })
  fireEvent.change(screen.getByLabelText('Variables'), { target: { value: '{"limit":3}' } })
  fireEvent.change(screen.getByLabelText('Delivery token (optional)'), { target: { value: 'delivery-secret' } })
  fireEvent.click(screen.getByRole('button', { name: 'Run query' }))

  await waitFor(() => expect(screen.getByRole('status').textContent).toBe(JSON.stringify(result, null, 2)))
  expect(fetch).toHaveBeenCalledExactlyOnceWith('/delivery/graphql', {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: 'Bearer delivery-secret' },
    body: JSON.stringify({ query, variables: { limit: 3 } }),
  })
  expect(readJson).toHaveBeenCalledOnce()
  expect(gql).not.toHaveBeenCalled()
  expect((screen.getByRole('button', { name: 'Run query' }) as HTMLButtonElement).disabled).toBe(false)
})

test.each(['', 'delivery-secret'])('invalid variables make no request with token %j and clear busy state', async token => {
  render(<Explorer types={[]} />)
  fireEvent.change(screen.getByLabelText('Variables'), { target: { value: '{invalid' } })
  fireEvent.change(screen.getByLabelText('Delivery token (optional)'), { target: { value: token } })
  fireEvent.click(screen.getByRole('button', { name: 'Run query' }))

  await waitFor(() => expect(screen.getByRole('status').textContent).toMatch(/Expected|Unexpected/))
  expect(gql).not.toHaveBeenCalled()
  expect(fetch).not.toHaveBeenCalled()
  expect((screen.getByRole('button', { name: 'Run query' }) as HTMLButtonElement).disabled).toBe(false)
})

test.each(['gql', 'fetch', 'json'])('%s errors use the shared message formatter and clear busy state', async source => {
  const reason = new ApiError('Query unavailable', 'QUERY_FAILED', 'request-14')
  const readJson = vi.fn()
  if (source === 'gql') {
    vi.mocked(gql).mockRejectedValue(reason)
  } else if (source === 'fetch') {
    vi.mocked(fetch).mockRejectedValue(reason)
  } else {
    readJson.mockRejectedValue(reason)
    vi.mocked(fetch).mockResolvedValue({ json: readJson } as unknown as Response)
  }
  render(<Explorer types={[]} />)
  if (source !== 'gql') {
    fireEvent.change(screen.getByLabelText('Delivery token (optional)'), { target: { value: 'delivery-secret' } })
  }
  fireEvent.click(screen.getByRole('button', { name: 'Run query' }))

  await waitFor(() => expect(screen.getByRole('status').textContent).toBe(message(reason)))
  expect((screen.getByRole('button', { name: 'Run query' }) as HTMLButtonElement).disabled).toBe(false)
  if (source === 'gql') {
    expect(gql).toHaveBeenCalledOnce()
    expect(fetch).not.toHaveBeenCalled()
  } else {
    expect(fetch).toHaveBeenCalledOnce()
    expect(gql).not.toHaveBeenCalled()
    expect(readJson).toHaveBeenCalledTimes(source === 'json' ? 1 : 0)
  }
})

test.each(['editorial', 'delivery'])('%s requests disable the run button until they finish', async mode => {
  let resolve!: (value: object) => void
  const pending = new Promise<object>(complete => { resolve = complete })
  if (mode === 'editorial') {
    vi.mocked(gql).mockReturnValue(pending)
  } else {
    vi.mocked(fetch).mockResolvedValue({ json: vi.fn().mockReturnValue(pending) } as unknown as Response)
  }
  render(<Explorer types={[]} />)
  if (mode === 'delivery') {
    fireEvent.change(screen.getByLabelText('Delivery token (optional)'), { target: { value: 'delivery-secret' } })
  }
  fireEvent.click(screen.getByRole('button', { name: 'Run query' }))

  const button = screen.getByRole('button', { name: 'Running…' }) as HTMLButtonElement
  expect(button.disabled).toBe(true)
  expect(screen.getByRole('status').textContent).toBe('Run a query to see its result.')
  fireEvent.click(button)
  expect(mode === 'editorial' ? gql : fetch).toHaveBeenCalledOnce()

  const result = { total: 0 }
  await act(async () => { resolve(result) })
  expect(screen.getByRole('status').textContent).toBe(JSON.stringify(result, null, 2))
  expect((screen.getByRole('button', { name: 'Run query' }) as HTMLButtonElement).disabled).toBe(false)
})

test('generated typed query labels capitalize only the first character and preserve their spaces', () => {
  const types: ContentType[] = [
    { id: 'type-1', key: 'post', name: 'Post', fields: [], version: 1 },
    { id: 'type-2', key: 'landingPage', name: 'Landing page', fields: [], version: 1 },
  ]
  const { container } = render(<Explorer types={types} />)

  expect(Array.from(container.querySelectorAll('.plain-card:first-of-type > p code'), code => code.textContent)).toEqual(['allCmsPost ', 'allCmsLandingPage '])
  expect(container.querySelector('.plain-card p')?.textContent).toBe('Generated typed queries: allCmsPost allCmsLandingPage ')
  expect(gql).not.toHaveBeenCalled()
  expect(fetch).not.toHaveBeenCalled()
})
