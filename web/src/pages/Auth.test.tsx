import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { Auth } from './Auth'

afterEach(() => { cleanup(); vi.unstubAllGlobals(); location.hash = '' })
it('distinguishes personal and workspace names and explains the password rule before submission', () => {
  render(<Auth initialized={false} providers={[]} me={null} onSuccess={vi.fn()} />)
  expect(screen.getByLabelText('Your name')).toBeDefined()
  expect(screen.getByLabelText('Workspace name')).toBeDefined()
  expect(screen.getByLabelText('Email').getAttribute('type')).toBe('email')
  expect(screen.getByLabelText('Password').getAttribute('aria-describedby')).toBe('password-help')
  expect(screen.getByText('Use at least 12 characters.')).toBeDefined()
})
it('shows configured OAuth providers without exposing provider credentials', () => {
  render(<Auth initialized providers={[{ id: 'oidc', name: 'Company SSO' }]} me={null} onSuccess={vi.fn()} />)
  expect(screen.getByRole('link', { name: 'Continue with Company SSO' }).getAttribute('href')).toBe('/auth/oauth/oidc/start')
})
it('keeps login input values and displays the server error after failed sign-in', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, json: async () => ({ detail: 'Invalid email or password.' }) }))
  render(<Auth initialized providers={[]} me={null} onSuccess={vi.fn()} />)
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'reader@example.com' } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'wrong-password' } })
  fireEvent.submit(screen.getByRole('button', { name: 'Sign in' }).closest('form')!)
  expect((await screen.findByRole('alert')).textContent).toBe('Invalid email or password.')
  expect((screen.getByLabelText('Email') as HTMLInputElement).value).toBe('reader@example.com')
  expect(screen.getByLabelText('Email').getAttribute('type')).toBe('text')
  expect(screen.getByLabelText('Email').getAttribute('inputmode')).toBe('email')
})

it('renders the same sign-in error for an unknown email and a wrong password', async () => {
  async function signIn(email: string, body: { detail: string; code?: string }, requestId: string) {
    cleanup()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      json: async () => body,
      headers: new Headers({ 'X-Request-ID': requestId }),
    }))
    render(<Auth initialized providers={[]} me={null} onSuccess={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: email } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'wrong-password' } })
    fireEvent.submit(screen.getByRole('button', { name: 'Sign in' }).closest('form')!)
    return (await screen.findByRole('alert')).textContent
  }
  const unknown = await signIn('nobody@example.com', { detail: 'Invalid email or password.' }, 'request-unknown')
  const wrong = await signIn('admin@example.com', { detail: 'Invalid email or password.', code: 'UNAUTHORIZED' }, 'request-wrong')
  expect(unknown).toBe('Invalid email or password.')
  expect(wrong).toBe(unknown)
})

it('submits a Hebrew email and shows the API result without throwing', async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce({
      ok: false,
      json: async () => ({ detail: 'Invalid email or password.' }),
      headers: new Headers({ 'X-Request-ID': 'request-hebrew' }),
    })
    .mockResolvedValueOnce({
      ok: false,
      json: async () => ({ detail: 'Enter a valid email address.', code: 'VALIDATION' }),
      headers: new Headers({ 'X-Request-ID': 'request-reject' }),
    })
  vi.stubGlobal('fetch', fetchMock)
  render(<Auth initialized providers={[]} me={null} onSuccess={vi.fn()} />)
  const email = 'משתמש@דוגמה.קום'
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: email } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'wrong-password' } })
  fireEvent.submit(screen.getByRole('button', { name: 'Sign in' }).closest('form')!)
  expect((await screen.findByRole('alert')).textContent).toBe('Invalid email or password.')
  expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body)).email).toBe(email)
  cleanup()
  vi.stubGlobal('fetch', fetchMock)
  render(<Auth initialized providers={[]} me={null} onSuccess={vi.fn()} />)
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'משתמש@דוגמה' } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'wrong-password' } })
  fireEvent.submit(screen.getByRole('button', { name: 'Sign in' }).closest('form')!)
  expect((await screen.findByRole('alert')).textContent).toContain('Enter a valid email address.')
  expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body)).email).toBe('משתמש@דוגמה')
})


it('preserves an entry deep link and list context after successful sign-in', async () => {
  const hash = '#content?workspace=workspace-a&entry=entry-a&type=article&search=hello&sort=title_asc'
  history.replaceState(null, '', hash)
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) }))
  const success = vi.fn()
  render(<Auth initialized providers={[]} me={null} onSuccess={success} />)
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'editor@example.test' } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'password' } })
  fireEvent.submit(screen.getByRole('button', { name: 'Sign in' }).closest('form')!)
  await waitFor(() => expect(success).toHaveBeenCalledOnce())
  expect(location.hash).toBe(hash)
})

it('leaves password-recovery token routes after successful reset', async () => {
  history.replaceState(null, '', '#reset/recovery-token')
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) }))
  const success = vi.fn()
  render(<Auth initialized providers={[]} me={null} onSuccess={success} />)
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'editor@example.test' } })
  fireEvent.change(screen.getByLabelText('New password'), { target: { value: 'new-password-long' } })
  fireEvent.submit(screen.getByRole('button', { name: 'Set password' }).closest('form')!)
  await waitFor(() => expect(success).toHaveBeenCalledOnce())
  expect(location.hash).toBe('#content')
})
