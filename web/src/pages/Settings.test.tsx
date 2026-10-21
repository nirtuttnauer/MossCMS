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
