import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Content } from './Content'
import { gql, type ContentType, type Entry } from '../lib/api'

vi.mock('../lib/api', async importOriginal => ({
  ...(await importOriginal<typeof import('../lib/api')>()),
  gql: vi.fn(),
}))

describe('Navigation and Content-List Context (MC-36)', () => {
  const types: ContentType[] = [
    { id: 't1', key: 'article', name: 'Articles', version: 1, fields: [{ name: 'title', type: 'text' }] },
    { id: 't2', key: 'product', name: 'Products', version: 1, fields: [{ name: 'title', type: 'text' }] },
  ]

  const entries: Entry[] = [
    {
      id: 'entry-alpha',
      typeKey: 'article',
      slug: 'alpha-post',
      title: 'Alpha Post',
      data: { title: 'Alpha Post' },
      status: 'published',
      version: 1,
      updatedAt: '2026-10-08T12:00:00Z',
      isLive: true,
      hasUnpublishedChanges: false,
    },
    {
      id: 'entry-beta',
      typeKey: 'product',
      slug: 'beta-item',
      title: 'Beta Item',
      data: { title: 'Beta Item' },
      status: 'draft',
      version: 1,
      updatedAt: '2026-10-09T12:00:00Z',
      isLive: false,
      hasUnpublishedChanges: false,
    },
  ]

  beforeEach(() => {
    vi.restoreAllMocks()
    location.hash = ''
    history.replaceState(null, '', '/')
    vi.mocked(gql).mockImplementation(async (query, vars: any) => {
      if (query.includes('entries(')) {
        return {
          entries: { nodes: entries, total: 2, hasNextPage: false, endCursor: null },
          contentGroups: [
            { key: 'article', name: 'Articles', count: 1 },
            { key: 'product', name: 'Products', count: 1 },
          ],
        }
      }
      if (query.includes('entry(')) {
        const found = entries.find(e => e.id === vars?.id)
        if (found) return { entry: found }
        throw new Error('Entry not found')
      }
      return { entries: { nodes: [] }, assets: [] }
    })
  })

  afterEach(() => {
    cleanup()
    location.hash = ''
    history.replaceState(null, '', '/')
  })

  it('restores filters and sorting from URL hash parameters on load', async () => {
    location.hash = '#content?type=article&status=published&search=Alpha&sort=title_asc'

    render(<Content types={types} role="editor" onChanged={vi.fn()} />)

    await screen.findByDisplayValue('Alpha')
    const typeSelect = screen.getByLabelText('Content type') as HTMLSelectElement
    const statusSelect = screen.getByLabelText('Publishing status') as HTMLSelectElement
    const sortSelect = screen.getByLabelText('Sort entries') as HTMLSelectElement

    expect(typeSelect.value).toBe('article')
    expect(statusSelect.value).toBe('published')
    expect(sortSelect.value).toBe('title_asc')
  })

  it('updates URL hash when filters change without full reload', async () => {
    render(<Content types={types} role="editor" onChanged={vi.fn()} />)
    await screen.findByText('Alpha Post')

    const statusSelect = screen.getByLabelText('Publishing status')
    fireEvent.change(statusSelect, { target: { value: 'draft' } })

    expect(location.hash).toContain('status=draft')
  })

  it('opens entry directly from URL entry parameter and closes back to list', async () => {
    location.hash = '#content?entry=entry-alpha'

    render(<Content types={types} role="editor" onChanged={vi.fn()} />)

    // The editor page should open automatically for entry-alpha
    await screen.findByRole('heading', { name: 'Alpha Post', level: 1 })
    expect(screen.getByDisplayValue('alpha-post')).toBeTruthy()

    // Closing returns to originating list and removes entry from hash
    fireEvent.click(screen.getByRole('button', { name: 'Back to content' }))
    await waitFor(() => expect(screen.queryByRole('region', { name: 'Entry editor' })).toBeNull())
    expect(location.hash).not.toContain('entry=entry-alpha')
  })

  it('copies clean entry link to clipboard without leaking tokens or private data', async () => {
    let clipboardText = ''
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn(async (text: string) => {
          clipboardText = text
        }),
      },
    })

    render(<Content types={types} role="editor" onChanged={vi.fn()} />)
    await screen.findByText('Alpha Post')

    const copyBtns = screen.getAllByRole('button', { name: 'Copy link' })
    fireEvent.click(copyBtns[0])

    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalled())
    expect(clipboardText).toContain('#content?')
    expect(clipboardText).toContain('entry=entry-alpha')
    // Must never leak auth/session/csrf/preview tokens
    expect(clipboardText).not.toContain('token')
    expect(clipboardText).not.toContain('csrf')
    expect(clipboardText).not.toContain('session')
  })

  it('handles missing or denied entries gracefully without crashing or leaking other workspace data', async () => {
    location.hash = '#content?entry=non-existent-or-forbidden-id'

    render(<Content types={types} role="editor" onChanged={vi.fn()} />)

    await screen.findByText('Entry not found or access denied.')
    expect(screen.queryByRole('region', { name: 'Entry editor' })).toBeNull()
    expect(location.hash).not.toContain('entry=non-existent')
  })
})

it('canceling browser navigation preserves the dirty form and restores its route', async () => {
  vi.spyOn(window, 'confirm').mockReturnValue(false)
  render(<Content types={[{ id: 't', key: 'article', name: 'Articles', version: 1, fields: [{ name: 'title', type: 'text' }] }]} role="editor" onChanged={vi.fn()} />)
  fireEvent.click(await screen.findByRole('button', { name: 'New entry' }))
  fireEvent.change(screen.getByLabelText(/^title/), { target: { value: 'Unsaved wording' } })
  const route = location.hash
  history.replaceState(null, '', '#content')
  window.dispatchEvent(new PopStateEvent('popstate'))
  expect(location.hash).toBe(route)
  expect(screen.getByDisplayValue('Unsaved wording')).toBeTruthy()
})
