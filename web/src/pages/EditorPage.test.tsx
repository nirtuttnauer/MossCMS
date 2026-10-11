import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { gql, type Entry } from '../lib/api'
import { Content } from './Content'
import { Types } from './Types'
import { PublicationQueue } from './PublicationQueue'

vi.mock('../lib/api', async original => ({ ...await original<typeof import('../lib/api')>(), gql: vi.fn() }))
const types = [{ id: 'article-type', key: 'article', name: 'Articles', version: 1, fields: [{ name: 'title', type: 'text', required: true }] }]
const entry: Entry = { id: 'article-id', typeKey: 'article', slug: 'thoughtful-design', title: 'Thoughtful design', data: { title: 'Thoughtful design' }, status: 'draft', version: 1, updatedAt: '2026-10-11T12:00:00Z', isLive: false, hasUnpublishedChanges: false }
beforeEach(() => {
  history.replaceState(null, '', '#content')
  vi.spyOn(window, 'confirm').mockReturnValue(true)
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
  vi.mocked(gql).mockImplementation(async () => ({ entries: { nodes: [entry], total: 1, hasNextPage: false, endCursor: null }, contentGroups: [{ key: 'article', name: 'Articles', count: 1 }], assets: [], publicationQueue: { nodes: [entry], total: 1 } }))
})
afterEach(() => { cleanup(); history.replaceState(null, '', '#content'); vi.restoreAllMocks() })

test('entry editing replaces the library and returning preserves the type filter', async () => {
  render(<Content types={types} role="editor" onChanged={vi.fn()} />)
  fireEvent.change(screen.getByRole('combobox', { name: 'Content type' }), { target: { value: 'article' } })
  fireEvent.click(await screen.findByRole('button', { name: 'Edit' }))
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(screen.queryByRole('region', { name: 'Entries' })).toBeNull()
  expect(document.activeElement).toBe(screen.getByRole('heading', { level: 1, name: entry.title }))
  expect(new URLSearchParams(location.hash.split('?')[1]).get('entry')).toBe(entry.id)
  fireEvent.click(screen.getByRole('button', { name: 'Back to content' }))
  expect(screen.getByRole('region', { name: 'Entries' })).toBeTruthy()
  expect((screen.getByRole('combobox', { name: 'Content type' }) as HTMLSelectElement).value).toBe('article')
})

test('new entry is a page that closes when browser history returns to the library', async () => {
  render(<Content types={types} role="editor" onChanged={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: 'New entry' }))
  expect(new URLSearchParams(location.hash.split('?')[1]).get('entry')).toBe('new')
  expect(screen.getByRole('heading', { level: 1, name: 'New entry' })).toBeTruthy()
  history.replaceState(null, '', '#content')
  window.dispatchEvent(new PopStateEvent('popstate'))
  await waitFor(() => expect(screen.queryByRole('button', { name: 'Back to content' })).toBeNull())
})

test('content type builder replaces its list and returns without a dialog', () => {
  render(<Types types={types} role="admin" onChanged={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: 'New type' }))
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(screen.queryByRole('button', { name: 'Edit schema' })).toBeNull()
  expect(screen.getByRole('complementary', { name: 'Content type previews' })).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Back to content types' }))
  expect(screen.getByRole('button', { name: 'Edit schema' })).toBeTruthy()
})

test('publication editing uses the same page and returns to the queue', async () => {
  render(<PublicationQueue types={types} role="editor" onChanged={vi.fn()} />)
  fireEvent.click(await screen.findByRole('button', { name: 'Edit / replace schedule' }))
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(screen.queryByRole('button', { name: 'Refresh queue' })).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Back to publications' }))
  expect(screen.getByRole('button', { name: 'Refresh queue' })).toBeTruthy()
})
