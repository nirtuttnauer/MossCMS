import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ReferencePicker } from './ReferencePicker'
import { getContext, gql, setContext, type Entry } from '../lib/api'

vi.mock('../lib/api', async importOriginal => ({
  ...await importOriginal<typeof import('../lib/api')>(),
  gql: vi.fn(),
}))

let previousContext: ReturnType<typeof getContext>

beforeEach(() => {
  previousContext = getContext()
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.clearAllMocks()
  setContext(previousContext.project, previousContext.csrf)
})

describe('ReferencePicker (TASK-37)', () => {
  it('discards stale searches and resets the cursor when the search changes', async () => {
    const entry = (id: string, title: string) => ({ id, title, typeKey: 'author', slug: id, data: {}, status: 'draft', version: 1, updatedAt: '', isLive: false, hasUnpublishedChanges: false })
    let oldResolve!: (value: unknown) => void
    vi.mocked(gql).mockImplementation(async (_query, vars) => {
      if (vars?.search === 'old') return new Promise(resolve => { oldResolve = resolve })
      return { entries: { nodes: vars?.search === 'new' ? [entry('new', 'Current result')] : [], total: 0, endCursor: null, hasNextPage: false } }
    })
    render(<ReferencePicker label="Author" value={null} onChange={vi.fn()} target="author" />)
    fireEvent.click(screen.getByRole('button', { name: 'Choose reference' }))
    const search = screen.getByLabelText('Search reference targets')
    fireEvent.change(search, { target: { value: 'old' } })
    await waitFor(() => expect(oldResolve).toBeTruthy())
    fireEvent.change(search, { target: { value: 'new' } })
    await screen.findByRole('button', { name: /Current result/ })
    oldResolve({ entries: { nodes: [entry('old', 'Stale result')], total: 1, endCursor: null, hasNextPage: false } })
    await waitFor(() => expect(screen.queryByRole('button', { name: /Stale result/ })).toBeNull())
    expect(vi.mocked(gql).mock.calls.find(([, vars]) => vars?.search === 'new')?.[1]?.after).toBeNull()
  })
  it('does not display a pending result from the previous workspace', async () => {
    let resolve!: (value: unknown) => void
    setContext('previous', 'csrf')
    vi.mocked(gql).mockImplementation(async (_query, vars, context) => {
      if (context?.project === 'previous' && vars?.id) return new Promise(done => { resolve = done })
      return { entry: null }
    })
    const view = render(<ReferencePicker label="Author" value="old-id" onChange={vi.fn()} projectId="previous" />)
    await waitFor(() => expect(resolve).toBeTruthy())
    setContext('next', 'csrf')
    view.rerender(<ReferencePicker label="Author" value="old-id" onChange={vi.fn()} projectId="next" />)
    await screen.findByText(/Selected target unavailable/)
    resolve({ entry: { id: 'old-id', title: 'Private old title', typeKey: 'author', status: 'draft', isLive: false } })
    await waitFor(() => expect(screen.queryByText('Private old title')).toBeNull())
  })
  it('finds and selects targets beyond the initial 100 entries with pagination and search', async () => {
    // Generate 160 entries
    const allEntries: Entry[] = Array.from({ length: 160 }, (_, i) => ({
      id: `entry-${i + 1}`,
      typeKey: i % 2 === 0 ? 'author' : 'topic',
      slug: `slug-${i + 1}`,
      title: `Author Title ${i + 1}`,
      data: {},
      status: 'published',
      version: 1,
      updatedAt: '2026-10-11T12:00:00Z',
      isLive: true,
      hasUnpublishedChanges: false,
    }))

    vi.mocked(gql).mockImplementation(async (query, vars: any) => {
      if (query.includes('entries(')) {
        const type = vars?.typeKey
        const search = (vars?.search || '').toLowerCase()
        const after = vars?.after
        const first = vars?.first || 20

        let filtered = allEntries.filter(e => !type || e.typeKey === type)
        if (search) {
          filtered = filtered.filter(e => e.title.toLowerCase().includes(search) || e.slug.toLowerCase().includes(search))
        }

        const startIndex = after ? filtered.findIndex(e => e.id === after) + 1 : 0
        const pageNodes = filtered.slice(startIndex, startIndex + first)
        const hasNext = startIndex + first < filtered.length
        const endCursor = pageNodes.length ? pageNodes[pageNodes.length - 1].id : null

        return {
          entries: {
            nodes: pageNodes,
            total: filtered.length,
            endCursor,
            hasNextPage: hasNext,
          },
        }
      }
      if (query.includes('entry(')) {
        const found = allEntries.find(e => e.id === vars?.id)
        if (!found) throw new Error('Not found')
        return { entry: found }
      }
      return {}
    })

    const onChange = vi.fn()
    render(<ReferencePicker label="Author" value={null} onChange={onChange} target="author" />)

    // Open picker
    fireEvent.click(screen.getByRole('button', { name: 'Choose reference' }))

    // Initial page has first 20 author entries
    await screen.findByRole('button', { name: /^Author Title 1\b/ })
    expect(screen.getByText('Showing 20 of 80 matching entries.').getAttribute('role')).toBe('status')

    // Paginate forward multiple times to reach entries beyond 100
    // Click Next references
    const nextBtn = screen.getByRole('button', { name: 'Next references' })
    expect((nextBtn as HTMLButtonElement).disabled).toBe(false)

    // Three cursor advances reach the fourth page (author 121).
    for (const title of [41, 81, 121]) {
      fireEvent.click(nextBtn)
      await screen.findByRole('button', { name: new RegExp(`^Author Title ${title}\\b`) })
    }

    fireEvent.click(screen.getByRole('button', { name: 'Previous references' }))
    await screen.findByRole('button', { name: /^Author Title 81\b/ })
    expect(vi.mocked(gql).mock.calls[vi.mocked(gql).mock.calls.length - 1]?.[1]?.after).toBe('entry-79')

    // Search directly for item 155 (outside initial 100)
    const searchInput = screen.getByLabelText('Search reference targets')
    fireEvent.change(searchInput, { target: { value: '155' } })

    // Entry 155 (even number is author: 154 is author, 155 is topic, 150 is author)
    fireEvent.change(searchInput, { target: { value: '151' } })

    const option151 = await screen.findByRole('button', { name: /Author Title 151/ })
    expect(option151).toBeTruthy()

    // Select entry 150
    fireEvent.click(option151)
    expect(onChange).toHaveBeenCalledWith('entry-151')
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Choose reference' })))
  })

  it('displays stored selection label even when absent from current search, and handles unavailable target safely', async () => {
    vi.mocked(gql).mockImplementation(async (query, vars: any) => {
      if (query.includes('entry(')) {
        if (vars?.id === 'deleted-target') {
          return {
            entry: {
              id: 'deleted-target',
              typeKey: 'author',
              slug: 'deleted-author',
              title: 'Trashed Author',
              data: {},
              status: 'deleted',
              version: 2,
              updatedAt: '2026-10-11T12:00:00Z',
              isLive: false,
              hasUnpublishedChanges: false,
            },
          }
        }
        if (vars?.id === 'stored-far-away') {
          return {
            entry: {
              id: 'stored-far-away',
              typeKey: 'author',
              slug: 'remote-author',
              title: 'Remote Author',
              data: {},
              status: 'draft',
              version: 1,
              updatedAt: '2026-10-11T12:00:00Z',
              isLive: false,
              hasUnpublishedChanges: false,
            },
          }
        }
        throw new Error('Not found')
      }
      return { entries: { nodes: [], total: 0, endCursor: null, hasNextPage: false } }
    })

    const onChange = vi.fn()
    const { rerender } = render(<ReferencePicker label="Author" value="stored-far-away" onChange={onChange} target="author" />)

    // Stored selection displays label independently of search page
    await screen.findByText('Remote Author')
    expect(screen.getByText('(author)')).toBeTruthy()
    // Displays draft warning
    expect(screen.getByText(/Draft target: will not resolve in public delivery until published/)).toBeTruthy()

    // Re-render with deleted/unavailable target
    rerender(<ReferencePicker label="Author" value="deleted-target" onChange={onChange} target="author" />)
    await screen.findByText('In trash')
    expect(screen.getByText(/The selected entry is deleted or inaccessible/)).toBeTruthy()

    // Clear selection works
    const clearBtn = screen.getByRole('button', { name: 'Clear' })
    fireEvent.click(clearBtn)
    expect(onChange).toHaveBeenCalledWith(null)
  })

  it('provides accessible loading, no-results, and error/retry states', async () => {
    let failOnce = true
    vi.mocked(gql).mockImplementation(async query => {
      if (query.includes('entries(')) {
        if (failOnce) {
          failOnce = false
          throw new Error('Network error loading targets')
        }
        return { entries: { nodes: [], total: 0, endCursor: null, hasNextPage: false } }
      }
      return {}
    })

    render(<ReferencePicker label="Topic" value={null} onChange={vi.fn()} target="topic" />)

    fireEvent.click(screen.getByRole('button', { name: 'Choose reference' }))

    // Error state appears with Retry
    await screen.findByRole('alert')
    expect(screen.getByText('Network error loading targets')).toBeTruthy()

    const retryBtn = screen.getByRole('button', { name: 'Retry' })
    fireEvent.click(retryBtn)

    // After retry succeeds with empty nodes, shows no matching entries
    await screen.findByText('No matching entries.')
  })
})


describe('ReferencePicker request lifecycle', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    setContext('current', 'csrf')
  })

  const entry: Entry = {
    id: 'current-target',
    title: 'Current target',
    typeKey: 'author',
    slug: 'current-target',
    data: {},
    status: 'draft',
    version: 1,
    updatedAt: '',
    isLive: false,
    hasUnpublishedChanges: false,
  }

  it('waits 200 ms and coalesces rapid searches into the latest request', async () => {
    vi.mocked(gql).mockResolvedValue({ entries: { nodes: [], total: 0, endCursor: null, hasNextPage: false } })
    render(<ReferencePicker label="Author" value={null} onChange={vi.fn()} target="author" />)
    fireEvent.click(screen.getByRole('button', { name: 'Choose reference' }))

    await act(async () => { await vi.advanceTimersByTimeAsync(199) })
    expect(gql).not.toHaveBeenCalled()
    await act(async () => { await vi.advanceTimersByTimeAsync(1) })
    expect(gql).toHaveBeenCalledTimes(1)
    expect(vi.mocked(gql).mock.calls[0].slice(1)).toEqual([
      { typeKey: 'author', search: '', after: null, first: 20 },
      { project: 'current', csrf: 'csrf' },
    ])

    vi.mocked(gql).mockClear()
    const search = screen.getByLabelText('Search reference targets')
    fireEvent.change(search, { target: { value: 'first' } })
    await act(async () => { await vi.advanceTimersByTimeAsync(100) })
    fireEvent.change(search, { target: { value: 'latest' } })
    await act(async () => { await vi.advanceTimersByTimeAsync(199) })
    expect(gql).not.toHaveBeenCalled()
    await act(async () => { await vi.advanceTimersByTimeAsync(1) })
    expect(gql).toHaveBeenCalledTimes(1)
    expect(vi.mocked(gql).mock.calls[0][1]).toEqual({ typeKey: 'author', search: 'latest', after: null, first: 20 })
  })

  it.each(['close', 'unmount'])('cancels the debounce timer on %s', async action => {
    vi.mocked(gql).mockResolvedValue({ entries: { nodes: [], total: 0, endCursor: null, hasNextPage: false } })
    const view = render(<ReferencePicker label="Author" value={null} onChange={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Choose reference' }))
    await act(async () => { await vi.advanceTimersByTimeAsync(199) })
    if (action === 'close') {
      fireEvent.click(screen.getByRole('button', { name: 'Close reference picker' }))
    } else {
      view.unmount()
    }
    await act(async () => { await vi.advanceTimersByTimeAsync(201) })
    expect(gql).not.toHaveBeenCalled()
  })

  it('marks a stored selection with the wrong target type as unavailable and filters invalid choices', async () => {
    vi.mocked(gql).mockImplementation(async (_query, vars) => vars?.id
      ? { entry: { ...entry, typeKey: 'topic', title: 'Wrong target' } }
      : {
        entries: {
          nodes: [
            entry,
            { ...entry, id: 'wrong', typeKey: 'topic', title: 'Wrong target' },
            { ...entry, id: 'deleted', status: 'deleted', title: 'Deleted target' },
          ],
          total: 3,
          endCursor: null,
          hasNextPage: false,
        },
      })
    await act(async () => {
      render(<ReferencePicker label="Author" value="current-target" onChange={vi.fn()} target="author" />)
    })
    expect(screen.getByText(/Selected target unavailable/)).toBeTruthy()
    expect(screen.queryByText('Wrong target')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Choose reference' }))
    await act(async () => { await vi.advanceTimersByTimeAsync(200) })
    expect(screen.getByRole('button', { name: /Current target/ })).toBeTruthy()
    expect(screen.queryByText('Wrong target')).toBeNull()
    expect(screen.queryByText('Deleted target')).toBeNull()
  })

  it.each(['result', 'error'])('ignores a late page %s after closing and reopening', async outcome => {
    let resolve!: (value: unknown) => void
    let reject!: (reason: Error) => void
    vi.mocked(gql).mockImplementationOnce(() => new Promise((done, fail) => {
      resolve = done
      reject = fail
    })).mockResolvedValue({ entries: { nodes: [entry], total: 1, endCursor: null, hasNextPage: false } })
    render(<ReferencePicker label="Author" value={null} onChange={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Choose reference' }))
    await act(async () => { await vi.advanceTimersByTimeAsync(200) })
    fireEvent.click(screen.getByRole('button', { name: 'Close reference picker' }))
    fireEvent.click(screen.getByRole('button', { name: 'Choose reference' }))
    await act(async () => {
      if (outcome === 'result') {
        resolve({ entries: { nodes: [{ ...entry, title: 'Late target' }], total: 1, endCursor: null, hasNextPage: false } })
      } else {
        reject(new Error('Late page error'))
      }
    })
    expect(screen.getByText('Loading reference targets…')).toBeTruthy()
    expect(screen.queryByText('Late target')).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
    await act(async () => { await vi.advanceTimersByTimeAsync(200) })
    expect(screen.getByRole('button', { name: /Current target/ })).toBeTruthy()
  })

  it.each(['result', 'error'])('rejects selected and page %s when global workspace context changes', async outcome => {
    const pending: { resolve: (value: unknown) => void; reject: (reason: Error) => void }[] = []
    vi.mocked(gql).mockImplementation(() => new Promise((resolve, reject) => {
      pending.push({ resolve, reject })
    }))
    render(<ReferencePicker label="Author" value="current-target" onChange={vi.fn()} projectId="current" />)
    fireEvent.click(screen.getByRole('button', { name: 'Choose reference' }))
    await act(async () => { await vi.advanceTimersByTimeAsync(200) })
    expect(pending).toHaveLength(2)
    setContext('next', 'next-csrf')
    await act(async () => {
      if (outcome === 'result') {
        pending[0].resolve({ entry })
        pending[1].resolve({ entries: { nodes: [entry], total: 1, endCursor: null, hasNextPage: false } })
      } else {
        pending.forEach(request => request.reject(new Error('Private previous workspace error')))
      }
    })
    expect(screen.getByText('Loading selected reference…')).toBeTruthy()
    expect(screen.getByText('Loading reference targets…')).toBeTruthy()
    expect(screen.queryByText('Current target')).toBeNull()
    expect(screen.queryByText(/Selected target unavailable/)).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it.each(['project', 'target'])('resets search, pagination, and errors when %s changes', async changedProp => {
    vi.mocked(gql).mockResolvedValueOnce({ entries: { nodes: [entry], total: 2, endCursor: entry.id, hasNextPage: true } })
      .mockRejectedValueOnce(new Error('Page unavailable'))
      .mockResolvedValue({ entries: { nodes: [], total: 0, endCursor: null, hasNextPage: false } })
    const onChange = vi.fn()
    const view = render(<ReferencePicker label="Author" value={null} onChange={onChange} target="author" projectId="current" />)
    fireEvent.click(screen.getByRole('button', { name: 'Choose reference' }))
    fireEvent.change(screen.getByLabelText('Search reference targets'), { target: { value: 'old search' } })
    await act(async () => { await vi.advanceTimersByTimeAsync(200) })
    fireEvent.click(screen.getByRole('button', { name: 'Next references' }))
    await act(async () => { await vi.advanceTimersByTimeAsync(200) })
    expect(screen.getByRole('alert').textContent).toContain('Page unavailable')
    expect(vi.mocked(gql).mock.calls[1][1]?.after).toBe(entry.id)

    const projectId = changedProp === 'project' ? 'next' : 'current'
    const target = changedProp === 'target' ? 'topic' : 'author'
    setContext(projectId, 'csrf')
    view.rerender(<ReferencePicker label="Author" value={null} onChange={onChange} target={target} projectId={projectId} />)
    expect(screen.queryByLabelText('Search reference targets')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Choose reference' }))
    expect((screen.getByLabelText('Search reference targets') as HTMLInputElement).value).toBe('')
    expect(screen.queryByRole('alert')).toBeNull()
    await act(async () => { await vi.advanceTimersByTimeAsync(200) })
    expect(vi.mocked(gql).mock.calls[2].slice(1)).toEqual([
      { typeKey: target, search: '', after: null, first: 20 },
      { project: projectId, csrf: 'csrf' },
    ])
    expect((screen.getByRole('button', { name: 'Previous references' }) as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByText('No matching entries.')).toBeTruthy()
  })
})
