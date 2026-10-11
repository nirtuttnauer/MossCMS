import { afterEach, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { WorkspaceLocales } from './WorkspaceLocales'
import { rest } from '../lib/api'

vi.mock('../lib/api', async importOriginal => ({ ...(await importOriginal<typeof import('../lib/api')>()), rest: vi.fn() }))
afterEach(() => { cleanup(); vi.resetAllMocks() })
const project = { id: 'one', name: 'One', role: 'admin' as const, defaultLocale: 'en', locales: ['en'] }

it.each(['editor', 'reader'] as const)('keeps locale settings hidden for %s', role => {
  render(<WorkspaceLocales project={{ ...project, role }} onChanged={vi.fn()} />)
  expect(screen.queryByRole('button', { name: 'Save locales' })).toBeNull()
})
it.each([
  ['duplicate suggestions', 'en', 'en, en'],
  ['a missing default', 'en', 'he, fr-CA'],
  ['a padded default', ' en ', 'en, he'],
])('rejects %s without sending a write', async (_case, defaultLocale, locales) => {
  render(<WorkspaceLocales project={project} onChanged={vi.fn()} />)
  fireEvent.change(screen.getByLabelText('Default locale'), { target: { value: defaultLocale } })
  fireEvent.change(screen.getByLabelText('Suggested locales'), { target: { value: locales } })
  fireEvent.click(screen.getByRole('button', { name: 'Save locales' }))
  expect(await screen.findByRole('alert')).toBeTruthy()
  expect(rest).not.toHaveBeenCalled()
})
it('saves Hebrew defaults explicitly and preserves input after a server error', async () => {
  vi.mocked(rest).mockRejectedValueOnce(new Error('Locale settings changed. Retry.'))
  const onChanged = vi.fn()
  render(<WorkspaceLocales project={project} onChanged={onChanged} />)
  fireEvent.change(screen.getByLabelText('Default locale'), { target: { value: 'he' } })
  fireEvent.change(screen.getByLabelText('Suggested locales'), { target: { value: 'he, en' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save locales' }))
  expect((await screen.findByRole('alert')).textContent).toContain('Retry')
  expect(rest).toHaveBeenCalledWith('/api/projects/one', 'PATCH', { defaultLocale: 'he', locales: ['he', 'en'] })
  expect((screen.getByLabelText('Default locale') as HTMLInputElement).value).toBe('he')
  expect((screen.getByLabelText('Suggested locales') as HTMLInputElement).value).toBe('he, en')
  expect((screen.getByRole('button', { name: 'Save locales' }) as HTMLButtonElement).disabled).toBe(false)
  expect(onChanged).not.toHaveBeenCalled()
  expect(screen.queryByRole('status')).toBeNull()
})

it('trims suggestions, encodes the project id, and waits for the save before notifying', async () => {
  let resolveSave!: () => void
  vi.mocked(rest).mockImplementationOnce(() => new Promise(resolve => {
    resolveSave = () => resolve(undefined)
  }))
  const onChanged = vi.fn()
  render(<WorkspaceLocales project={{ ...project, id: 'one/two ?#' }} onChanged={onChanged} />)
  fireEvent.change(screen.getByLabelText('Suggested locales'), { target: { value: ' en , he , fr-CA ' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save locales' }))

  expect(rest).toHaveBeenCalledWith('/api/projects/one%2Ftwo%20%3F%23', 'PATCH', {
    defaultLocale: 'en',
    locales: ['en', 'he', 'fr-CA'],
  })
  expect((screen.getByRole('button', { name: 'Saving locales…' }) as HTMLButtonElement).disabled).toBe(true)
  expect(onChanged).not.toHaveBeenCalled()
  expect(screen.queryByRole('status')).toBeNull()

  await act(async () => resolveSave())
  expect(screen.getByRole('status').textContent).toBe('Locale defaults saved. Existing translations are preserved.')
  expect((screen.getByRole('button', { name: 'Save locales' }) as HTMLButtonElement).disabled).toBe(false)
  expect((screen.getByLabelText('Suggested locales') as HTMLInputElement).value).toBe(' en , he , fr-CA ')
  expect(onChanged).toHaveBeenCalledTimes(1)
})

it('resets edited inputs when locale props change and applies missing-value fallbacks', () => {
  const onChanged = vi.fn()
  const { rerender } = render(<WorkspaceLocales project={project} onChanged={onChanged} />)
  fireEvent.change(screen.getByLabelText('Default locale'), { target: { value: 'fr' } })
  fireEvent.change(screen.getByLabelText('Suggested locales'), { target: { value: 'fr, en' } })

  rerender(<WorkspaceLocales project={{ ...project, defaultLocale: 'he', locales: ['he', 'en'] }} onChanged={onChanged} />)
  expect((screen.getByLabelText('Default locale') as HTMLInputElement).value).toBe('he')
  expect((screen.getByLabelText('Suggested locales') as HTMLInputElement).value).toBe('he, en')

  rerender(<WorkspaceLocales project={{ ...project, defaultLocale: undefined, locales: undefined }} onChanged={onChanged} />)
  expect((screen.getByLabelText('Default locale') as HTMLInputElement).value).toBe('en')
  expect((screen.getByLabelText('Suggested locales') as HTMLInputElement).value).toBe('en')
  expect(rest).not.toHaveBeenCalled()
  expect(onChanged).not.toHaveBeenCalled()
})

it('clears old messages on retries and preserves inputs when a later save fails', async () => {
  let rejectSave!: (reason: Error) => void
  vi.mocked(rest)
    .mockRejectedValueOnce(new Error('First save failed.'))
    .mockResolvedValueOnce(undefined)
    .mockImplementationOnce(() => new Promise((_resolve, reject) => {
      rejectSave = reject
    }))
  const onChanged = vi.fn()
  render(<WorkspaceLocales project={project} onChanged={onChanged} />)
  fireEvent.change(screen.getByLabelText('Default locale'), { target: { value: 'he' } })
  fireEvent.change(screen.getByLabelText('Suggested locales'), { target: { value: 'he, en' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save locales' }))
  expect((await screen.findByRole('alert')).textContent).toBe('First save failed.')

  fireEvent.click(screen.getByRole('button', { name: 'Save locales' }))
  expect(screen.queryByRole('alert')).toBeNull()
  await screen.findByRole('status')
  expect(onChanged).toHaveBeenCalledTimes(1)

  fireEvent.click(screen.getByRole('button', { name: 'Save locales' }))
  expect(screen.queryByRole('status')).toBeNull()
  expect(screen.queryByRole('alert')).toBeNull()
  await act(async () => rejectSave(new Error('Later save failed.')))
  expect(screen.getByRole('alert').textContent).toBe('Later save failed.')
  expect((screen.getByRole('button', { name: 'Save locales' }) as HTMLButtonElement).disabled).toBe(false)
  expect((screen.getByLabelText('Default locale') as HTMLInputElement).value).toBe('he')
  expect((screen.getByLabelText('Suggested locales') as HTMLInputElement).value).toBe('he, en')
  expect(onChanged).toHaveBeenCalledTimes(1)
})
