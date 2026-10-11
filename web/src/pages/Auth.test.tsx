import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { Auth } from './Auth'

afterEach(() => { cleanup(); vi.unstubAllGlobals(); location.hash = '' })
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
