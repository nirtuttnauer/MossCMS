import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { gql } from '../lib/api'
import { FieldInput, fieldInputId } from './Fields'
import { Dialog } from './ui/dialog'

vi.mock('../lib/api', async importOriginal => ({ ...await importOriginal<typeof import('../lib/api')>(), gql: vi.fn() }))

afterEach(() => { cleanup(); vi.clearAllMocks() })
const common = { references: [], assets: [] }
describe('schema field editors', () => {
  it('preserves translations when one locale changes', () => {
    const change = vi.fn()
    render(<FieldInput {...common} field={{ name: 'title', type: 'text', localized: true }} value={{ en: 'Hello', fr: 'Bonjour' }} onChange={change} />)
    fireEvent.change(screen.getByLabelText('fr'), { target: { value: 'Salut' } })
    expect(change).toHaveBeenLastCalledWith({ en: 'Hello', fr: 'Salut' })
  })
  it('edits nested objects without dropping sibling values', () => {
    const change = vi.fn()
    render(<FieldInput {...common} field={{ name: 'address', type: 'object', fields: [{ name: 'city', type: 'text' }, { name: 'zip', type: 'number' }] }} value={{ city: 'Old', zip: 100 }} onChange={change} />)
    fireEvent.change(screen.getByLabelText('city'), { target: { value: 'New' } })
    expect(change).toHaveBeenLastCalledWith({ city: 'New', zip: 100 })
  })
  it('writes numbers as numbers and cleared numbers as null', () => {
    const change = vi.fn()
    render(<FieldInput {...common} field={{ name: 'rating', type: 'number' }} value={3} onChange={change} />)
    fireEvent.change(screen.getByLabelText('rating'), { target: { value: '4.5' } })
    expect(change).toHaveBeenLastCalledWith(4.5)
    fireEvent.change(screen.getByLabelText('rating'), { target: { value: '' } })
    expect(change).toHaveBeenLastCalledWith(null)
  })
  it('filters reference options to the declared target type', async () => {
    const references = [{ id: 'a', typeKey: 'person', title: 'Author', slug: 'author', status: 'published', isLive: true }, { id: 'b', typeKey: 'article', title: 'Article', slug: 'article', status: 'published', isLive: true }] as Parameters<typeof FieldInput>[0]['references']
    vi.mocked(gql).mockResolvedValue({ entries: { nodes: references.filter(entry => entry.typeKey === 'person'), total: 1, endCursor: null, hasNextPage: false } })
    render(<FieldInput {...common} references={references} field={{ name: 'author', type: 'reference', target: 'person' }} value="" onChange={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Choose reference' }))
    expect(await screen.findByRole('button', { name: /Author/ })).toBeTruthy()
    expect(screen.queryByRole('button', { name: /Article/ })).toBeNull()
  })
  it('adds a suggested locale while preserving old translations and reports invalid/duplicate codes', () => {
    const change = vi.fn()
    render(<FieldInput {...common} field={{ name: 'title', type: 'text', localized: true }} value={{ fr: 'Bonjour', he: 'שלום' }} onChange={change} defaultLocale="he" locales={['he', 'en']} />)
    expect(screen.getByLabelText('he').getAttribute('dir')).toBe('auto')
    fireEvent.change(screen.getByLabelText('Suggested locale for title'), { target: { value: 'en' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add locale' }))
    expect(change).toHaveBeenCalledWith({ fr: 'Bonjour', he: 'שלום', en: null })
    fireEvent.change(screen.getByLabelText('New locale for title'), { target: { value: 'he' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add locale' }))
    expect(screen.getByRole('alert').textContent).toContain('already has a translation')
    fireEvent.change(screen.getByLabelText('New locale for title'), { target: { value: 'bad-locale-code' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add locale' }))
    expect(screen.getByRole('alert').textContent).toContain('Use a locale code')
  })
  it('associates nested validation errors with the input', () => {
    render(<FieldInput {...common} field={{ name: 'group', type: 'object', fields: [{ name: 'text', type: 'text' }] }} value={{ text: '' }} errors={{ 'data.group.text': 'Write a title.' }} onChange={vi.fn()} />)
    const input = screen.getByLabelText('text')
    expect(input.getAttribute('aria-invalid')).toBe('true')
    expect(document.getElementById(input.getAttribute('aria-describedby')!)?.textContent).toBe('Write a title.')
  })
  it('initializes localized fields in new list items using workspace defaults', () => {
    const change = vi.fn()
    render(<FieldInput {...common} field={{ name: 'cards', type: 'list', item: { name: '', type: 'object', fields: [{ name: 'title', type: 'text', localized: true }] } }} value={[]} defaultLocale="he" onChange={change} />)
    fireEvent.click(screen.getByRole('button', { name: 'Add item' }))
    expect(change).toHaveBeenCalledWith([{ title: { he: null } }])
  })
  it.each(['object', 'list', 'localized'])('provides a focusable group target for a %s validation summary link', kind => {
    const field = kind === 'object' ? { name: 'group', type: 'object', fields: [{ name: 'title', type: 'text' }] } : kind === 'list' ? { name: 'group', type: 'list', item: { name: '', type: 'text' } } : { name: 'group', type: 'text', localized: true }
    render(<FieldInput {...common} field={field} value={null} errors={{ 'data.group': 'Complete this group.' }} onChange={vi.fn()} />)
    const group = document.getElementById(fieldInputId('data.group'))!
    group.focus()
    expect(document.activeElement).toBe(group)
    expect(document.getElementById(group.getAttribute('aria-describedby')!)?.textContent).toBe('Complete this group.')
  })
  it('names the modal and handles Escape', () => {
    const close = vi.fn()
    render(<Dialog title="Edit content" open onClose={close}><input aria-label="Title" /></Dialog>)
    expect(screen.getByRole('dialog', { name: 'Edit content' })).toBeTruthy()
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
    expect(close).toHaveBeenCalledOnce()
  })
})
