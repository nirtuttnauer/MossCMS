import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { Team } from './Team'
import { rest } from '../lib/api'
vi.mock('../lib/api', async original => ({ ...await original<typeof import('../lib/api')>(), rest: vi.fn() }))
const team = { members: [{ id: 'one', name: 'Editor', email: 'editor@example.test', role: 'editor' }], invitations: [] }
beforeEach(() => { vi.clearAllMocks(); vi.mocked(rest).mockResolvedValue(team) })
afterEach(() => { cleanup(); vi.restoreAllMocks() })
test('team loading and failed reads never assert that invitations are absent, and Retry recovers', async () => {
  let reject!: (reason: Error) => void
  vi.mocked(rest).mockImplementationOnce(() => new Promise((_resolve, fail) => { reject = fail }))
  render(<Team role="admin" onChanged={vi.fn()} />)
  expect(screen.getByRole('status').textContent).toBe('Loading team…')
  expect(screen.queryByText('No pending invitations.')).toBeNull()
  await act(async () => reject(new Error('Team unavailable')))
  expect(screen.queryByText('No pending invitations.')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Retry loading team' }))
  await screen.findByText('No pending invitations.')
  expect(screen.queryByRole('alert')).toBeNull()
  expect(screen.getByText('editor@example.test')).toBeTruthy()
})
test('repeated invitation submission sends one request and reports completion', async () => {
  let resolve!: (result: { url: string }) => void
  vi.mocked(rest).mockImplementation(async (_path, method) => method === 'POST' ? new Promise(done => { resolve = done }) : team)
  render(<Team role="admin" onChanged={vi.fn()} />)
  await screen.findByText('No pending invitations.')
  fireEvent.change(screen.getByLabelText('Teammate email'), { target: { value: 'new@example.test' } })
  const form = screen.getByRole('button', { name: 'Create invitation' }).closest('form')!
  fireEvent.submit(form); fireEvent.submit(form)
  expect(vi.mocked(rest).mock.calls.filter(([, method]) => method === 'POST')).toHaveLength(1)
  expect((screen.getByRole('button', { name: 'Creating invitation…' }) as HTMLButtonElement).disabled).toBe(true)
  await act(async () => resolve({ url: 'https://moss.test/invite/synthetic' }))
  await waitFor(() => expect(screen.getByRole('status').textContent).toContain('Invitation created'))
  expect((screen.getByLabelText('Invitation link') as HTMLInputElement).value).toContain('/invite/synthetic')
})
