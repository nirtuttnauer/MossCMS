import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { getContext, gql, rest, type ContentType, type Me } from '../lib/api'

vi.mock('../lib/api', async original => ({ ...await original<typeof import('../lib/api')>(), gql: vi.fn(), rest: vi.fn() }))
// Keep these tests on the shell's workspace boundary; the checklist has its own workflow tests.
vi.mock('../components/OnboardingChecklist', () => ({ OnboardingChecklist: () => null }))

const account: Me = {
  user: { id: 'user', email: 'editor@example.test', name: 'Editor' }, csrf: 'csrf', providers: [], authSkipped: true,
  projects: [{ id: 'a', name: 'Workspace A', role: 'editor' }, { id: 'b', name: 'Workspace B', role: 'editor' }],
}
const schema = (key: string, name: string): ContentType => ({ id: key, key, name, version: 1, fields: [{ name: 'title', label: 'Title', type: 'text' }] })
const workspace = (key: string, name: string, total: number) => ({
  contentTypes: [schema(key, name)],
  overview: { total, published: 0, drafts: total, scheduled: 0, types: 1, assets: 0, members: 1 },
})
function deferred<T>() {
  let resolve!: (value: T) => void, reject!: (reason: Error) => void
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail })
  return { promise, resolve, reject }
}
function navigate(hash: string, event = 'hashchange') {
  history.replaceState(null, '', hash)
  fireEvent(window, new Event(event))
}

beforeEach(() => {
  vi.clearAllMocks()
  const saved = new Map<string, string>()
  vi.stubGlobal('localStorage', { getItem: (key: string) => saved.get(key) ?? null, setItem: (key: string, value: string) => saved.set(key, value), removeItem: (key: string) => saved.delete(key), clear: () => saved.clear() })
  history.replaceState(null, '', '/#content?workspace=a')
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true }))
  vi.mocked(rest).mockImplementation(async path => {
    if (path === '/auth/status') return { initialized: true, providers: [] }
    if (path === '/auth/me') return account
    throw new Error(`Unexpected REST request ${path}`)
  })
  vi.mocked(gql).mockImplementation(async (query, _variables, context) => {
    if (query.includes('contentTypes')) return getContext().project === 'a' ? workspace('alpha', 'Alpha schema', 37) : workspace('beta', 'Beta schema', 4)
    const key = (context || getContext()).project === 'a' ? 'alpha' : 'beta'
    return { entries: { nodes: [], total: 0, endCursor: null, hasNextPage: false }, assets: [], contentGroups: [{ key, name: `${key} entries`, count: 0 }] }
  })
})
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); history.replaceState(null, '', '/') })

describe('App workspace and navigation boundaries', () => {
  it('hides the previous workspace schemas and counts during a hash switch and after its load fails', async () => {
    const pending = deferred<ReturnType<typeof workspace>>()
    const normal = vi.mocked(gql).getMockImplementation()!
    vi.mocked(gql).mockImplementation((query, variables, context) => query.includes('contentTypes') && getContext().project === 'b' ? pending.promise : normal(query, variables, context))
    render(<App />)
    await screen.findByRole('option', { name: 'Alpha schema' })
    expect(screen.getByRole('link', { name: 'Content' }).textContent).toContain('37')
    navigate('#content?workspace=b&type=beta')
    await screen.findByText('Loading workspace…')
    expect((screen.getByLabelText('Workspace') as HTMLSelectElement).value).toBe('b')
    expect(screen.queryByRole('option', { name: 'Alpha schema' })).toBeNull()
    expect(screen.getByRole('link', { name: 'Content' }).textContent).toContain('—')
    await act(async () => pending.reject(new Error('Workspace load failed')))
    await screen.findByText('Workspace data unavailable. Use Retry above.')
    expect(screen.queryByRole('option', { name: 'Alpha schema' })).toBeNull()
    expect(screen.getByRole('link', { name: 'Content' }).textContent).not.toContain('37')
    expect(location.hash).toContain('type=beta')
  })

  it('discards a slow previous workspace response after an authorized back-style switch', async () => {
    const oldLoad = deferred<ReturnType<typeof workspace>>()
    const normal = vi.mocked(gql).getMockImplementation()!
    vi.mocked(gql).mockImplementation((query, variables, context) => query.includes('contentTypes') && getContext().project === 'a' ? oldLoad.promise : normal(query, variables, context))
    render(<App />)
    await screen.findByLabelText('Workspace')
    navigate('#content?workspace=b&type=beta', 'popstate')
    await screen.findByRole('option', { name: 'Beta schema' })
    await act(async () => oldLoad.resolve(workspace('alpha', 'Alpha schema', 37)))
    expect(screen.queryByRole('option', { name: 'Alpha schema' })).toBeNull()
    expect((screen.getByLabelText('Content type') as HTMLSelectElement).value).toBe('beta')
    expect(screen.getByRole('link', { name: 'Content' }).textContent).not.toContain('37')
  })

  it('preserves a valid type filter until the initial workspace schema has loaded', async () => {
    history.replaceState(null, '', '/#content?workspace=a&type=alpha&search=word&sort=title_asc')
    const pending = deferred<ReturnType<typeof workspace>>()
    const normal = vi.mocked(gql).getMockImplementation()!
    vi.mocked(gql).mockImplementation((query, variables, context) => query.includes('contentTypes') ? pending.promise : normal(query, variables, context))
    render(<App />)
    await screen.findByText('Loading workspace…')
    expect(location.hash).toContain('type=alpha')
    expect(screen.queryByLabelText('Content type')).toBeNull()
    await act(async () => pending.resolve(workspace('alpha', 'Alpha schema', 37)))
    await screen.findByRole('option', { name: 'Alpha schema' })
    expect((screen.getByLabelText('Content type') as HTMLSelectElement).value).toBe('alpha')
    expect(screen.getByDisplayValue('word')).toBeTruthy()
    expect((screen.getByLabelText('Sort entries') as HTMLSelectElement).value).toBe('title_asc')
    expect(location.hash).toContain('type=alpha')
  })

  it.each(['hashchange', 'popstate'])('keeps a dirty editor and its workspace when %s navigation is canceled', async event => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    render(<App />)
    // Scope to the header action; the empty state also offers creation after loading.
    const heading = await screen.findByRole('heading', { name: 'Content', level: 1 })
    fireEvent.click(within(heading.closest<HTMLElement>('.page-heading')!).getByRole('button', { name: 'New entry' }))
    fireEvent.change(await screen.findByLabelText('Title'), { target: { value: 'Unsaved wording' } })
    const editorHash = location.hash
    navigate('#content?workspace=b', event)
    await waitFor(() => expect(location.hash).toBe(editorHash))
    expect(window.confirm).toHaveBeenCalledOnce()
    expect(screen.getByDisplayValue('Unsaved wording')).toBeTruthy()
    expect((screen.getByLabelText('Workspace') as HTMLSelectElement).value).toBe('a')
    expect(screen.queryByText('Loading workspace…')).toBeNull()
  })
})
