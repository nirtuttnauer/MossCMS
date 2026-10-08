import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
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
