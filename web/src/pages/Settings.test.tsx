import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { Settings } from './Settings'
import { gql, rest, type Me, type Project } from '../lib/api'
import { confirmNavigation } from '../lib/unsaved'

vi.mock('../lib/api', async original => ({ ...await original<typeof import('../lib/api')>(), gql: vi.fn(), rest: vi.fn() }))
const project: Project = { id: 'workspace', name: 'Studio', role: 'admin', previewOrigin: '' }
const me: Me = { user: { id: 'user', name: 'Admin', email: 'admin@example.test' }, csrf: '', providers: [], projects: [project] }
const token = { id: 'token', name: 'Production website', scopes: [], expiresAt: '2027-01-01' }
function mount() { return render(<Settings project={project} me={me} providers={[]} types={[]} onChanged={vi.fn()} />) }
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(done => { resolve = done }); return { promise, resolve } }
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(gql).mockResolvedValue({ auditLog: [{ action: 'Saved entry' }] })
  vi.mocked(rest).mockImplementation(async path => path === '/api/tokens' ? [token] : { endpoints: [{ id: 'hook', url: 'https://frontend.test/events', enabled: true }], deliveries: [] })
})
afterEach(() => { cleanup(); vi.restoreAllMocks() })

test.each(['token', 'webhook'])('access-changing %s action can be canceled before any DELETE', async kind => {
  mount()
  fireEvent.click(await screen.findByRole('button', { name: kind === 'token' ? 'Revoke' : 'Disable webhook' }))
  const dialog = screen.getByRole('dialog')
  expect(dialog.textContent).toContain(kind === 'token' ? 'Production website' : 'https://frontend.test/events')
  expect(vi.mocked(rest).mock.calls.some(([, method]) => method === 'DELETE')).toBe(false)
  fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(vi.mocked(rest).mock.calls.some(([, method]) => method === 'DELETE')).toBe(false)
})

test('a failed revocation stays in its confirmation dialog and can be retried once', async () => {
  const pending = deferred<unknown>()
  const normal = vi.mocked(rest).getMockImplementation()!
  let deletes = 0
  vi.mocked(rest).mockImplementation((path, method, body) => {
    if (method !== 'DELETE') return normal(path, method, body)
    deletes++
    return deletes === 1 ? Promise.reject(new Error('Service unavailable')) : pending.promise
  })
  mount()
  fireEvent.click(await screen.findByRole('button', { name: 'Revoke' }))
  const dialog = screen.getByRole('dialog')
  fireEvent.click(within(dialog).getByRole('button', { name: 'Revoke token' }))
  expect((await within(dialog).findByRole('alert')).textContent).toContain('Service unavailable')
  fireEvent.click(within(dialog).getByRole('button', { name: 'Revoke token' }))
  expect((within(dialog).getByRole('button', { name: 'Updating access…' }) as HTMLButtonElement).disabled).toBe(true)
  fireEvent.click(within(dialog).getByRole('button', { name: 'Updating access…' }))
  expect(deletes).toBe(2)
  await act(async () => pending.resolve({}))
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  expect(screen.getByRole('status').textContent).toContain('Delivery token revoked')
})

test('dirty configuration protects navigation, reverting restores clean state, and successful save resets baseline', async () => {
  vi.spyOn(window, 'confirm').mockReturnValue(false)
  mount()
  await screen.findByText('Production website')
  const origin = screen.getByLabelText('Website preview origin')
  fireEvent.change(origin, { target: { value: 'https://preview.test' } })
  expect(confirmNavigation()).toBe(false)
  expect(window.confirm).toHaveBeenLastCalledWith('Discard unsaved settings changes? Saved settings will be kept.')
  fireEvent.change(origin, { target: { value: '' } })
  expect(confirmNavigation()).toBe(true)
  fireEvent.change(origin, { target: { value: 'https://preview.test' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save preview origin' }))
  await screen.findByText('Website preview origin saved.')
  expect(confirmNavigation()).toBe(true)
})

test('a webhook read failure does not hide tokens or audit history and Retry clears the error', async () => {
  const normal = vi.mocked(rest).getMockImplementation()!
  vi.mocked(rest).mockImplementation((path, method, body) => path === '/api/webhooks' ? Promise.reject(new Error('Webhook unavailable')) : normal(path, method, body))
  mount()
  expect((await screen.findByRole('alert')).textContent).toContain('Webhook unavailable')
  expect(screen.getByText('Production website')).toBeTruthy()
  expect(screen.getByLabelText('Audit history').textContent).toContain('Saved entry')
  expect(screen.getByText('Webhooks unavailable. Retry loading settings above.')).toBeTruthy()
  vi.mocked(rest).mockImplementation(normal)
  fireEvent.click(screen.getByRole('button', { name: 'Retry loading settings' }))
  await waitFor(() => expect(screen.queryByRole('alert')).toBeNull())
  expect(screen.getByRole('button', { name: 'Disable webhook' })).toBeTruthy()
})

const createdToken = 'created-delivery-token-value'
const createdDigest = 'digest-of-created-delivery-token'

test('dismiss, reload, and remount leave the delivery token value out of the list while revoke still deletes that row', async () => {
  const listed = { id: createdDigest, name: 'Website', scopes: ['article'], expiresAt: '2027-06-01T00:00:00Z', token: createdToken, secret: createdToken, digest: createdDigest }
  const normal = vi.mocked(rest).getMockImplementation()!
  vi.mocked(rest).mockImplementation((path, method, body) => {
    if (path === '/api/tokens' && method === 'POST') return Promise.resolve({ token: createdToken })
    if (path === '/api/tokens') return Promise.resolve([token, listed])
    return normal(path, method, body)
  })
  const writeText = vi.fn().mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
  const consoleSpies = (['log', 'info', 'debug', 'warn', 'error'] as const).map(method => vi.spyOn(console, method).mockImplementation(() => {}))
  localStorage.clear()
  sessionStorage.clear()
  const view = mount()
  await screen.findByText('Production website')
  for (const row of document.querySelectorAll('.member-row')) {
    expect(row.innerHTML).not.toContain(createdToken)
    expect(row.innerHTML).not.toContain(createdDigest)
  }
  fireEvent.change(screen.getByLabelText('Token name'), { target: { value: 'Website' } })
  fireEvent.submit(screen.getByRole('button', { name: 'Create delivery token' }).closest('form')!)
  expect((await screen.findByLabelText('New delivery token') as HTMLInputElement).value).toBe(createdToken)
  fireEvent.click(screen.getByRole('button', { name: 'Copy' }))
  expect(await screen.findByText('Token copied.')).toBeTruthy()
  expect(writeText).toHaveBeenCalledWith(createdToken)
  for (const row of document.querySelectorAll('.member-row')) {
    expect(row.innerHTML).not.toContain(createdToken)
    expect(row.innerHTML).not.toContain(createdDigest)
  }
  fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }))
  expect(screen.queryByLabelText('New delivery token')).toBeNull()
  expect(document.body.innerHTML).not.toContain(createdToken)
  expect(document.body.innerHTML).not.toContain(createdDigest)
  fireEvent.click(screen.getByRole('button', { name: 'Refresh delivery history' }))
  await screen.findByText('Website')
  expect(screen.queryByLabelText('New delivery token')).toBeNull()
  expect(document.body.innerHTML).not.toContain(createdToken)
  expect(document.body.innerHTML).not.toContain(createdDigest)
  expect(location.href).not.toContain(createdToken)
  expect(location.href).not.toContain(createdDigest)
  const stored = [localStorage, sessionStorage].flatMap(store => Array.from({ length: store.length }, (_, index) => {
    const key = store.key(index) ?? ''
    return `${key}=${store.getItem(key) ?? ''}`
  })).join('\n')
  expect(stored).not.toContain(createdToken)
  expect(stored).not.toContain(createdDigest)
  expect(consoleSpies.some(spy => spy.mock.calls.some(call => call.some(part => String(part).includes(createdToken))))).toBe(false)
  view.unmount()
  mount()
  const row = (await screen.findByText('Website')).closest('.member-row') as HTMLElement
  expect(screen.queryByLabelText('New delivery token')).toBeNull()
  expect(document.body.innerHTML).not.toContain(createdToken)
  expect(row.innerHTML).not.toContain(createdDigest)
  fireEvent.click(within(row).getByRole('button', { name: 'Revoke' }))
  const dialog = screen.getByRole('dialog')
  expect(dialog.textContent).toContain('Website')
  expect(dialog.textContent).not.toContain(createdToken)
  expect(dialog.innerHTML).not.toContain(createdDigest)
  fireEvent.click(within(dialog).getByRole('button', { name: 'Revoke token' }))
  await waitFor(() => expect(vi.mocked(rest).mock.calls.some(([path, method]) => path === `/api/tokens/${createdDigest}` && method === 'DELETE')).toBe(true))
  expect(document.body.innerHTML).not.toContain(createdToken)
})

test('token creation disables repeat submission and retains the one-time secret', async () => {
  const pending = deferred<{ token: string }>()
  const normal = vi.mocked(rest).getMockImplementation()!
  vi.mocked(rest).mockImplementation((path, method, body) => method === 'POST' && path === '/api/tokens' ? pending.promise : normal(path, method, body))
  mount()
  await screen.findByText('Production website')
  fireEvent.change(screen.getByLabelText('Token name'), { target: { value: 'Website' } })
  const form = screen.getByRole('button', { name: 'Create delivery token' }).closest('form')!
  fireEvent.submit(form); fireEvent.submit(form)
  expect(vi.mocked(rest).mock.calls.filter(([path, method]) => path === '/api/tokens' && method === 'POST')).toHaveLength(1)
  expect((screen.getByRole('button', { name: 'Creating token…' }) as HTMLButtonElement).disabled).toBe(true)
  await act(async () => pending.resolve({ token: 'one-time-test-token' }))
  expect((await screen.findByLabelText('New delivery token') as HTMLInputElement).value).toBe('one-time-test-token')
  expect(confirmNavigation()).toBe(true)
})
