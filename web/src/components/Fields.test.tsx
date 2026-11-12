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
    expect(screen.getByLabelText('he').getAttribute('dir')).toBe('rtl')
    expect(screen.getByLabelText('he').getAttribute('lang')).toBe('he')
    expect(screen.getByLabelText('fr').getAttribute('dir')).toBe('ltr')
    expect(screen.getByLabelText('fr').getAttribute('lang')).toBe('fr')
    expect(screen.getByLabelText('New locale for title').getAttribute('dir')).toBe('ltr')
    expect(screen.getByLabelText('Suggested locale for title').getAttribute('dir')).toBe('ltr')
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
  it('locks Hebrew and Arabic values to rtl with a matching lang, and Latin locales to ltr', () => {
    render(<FieldInput {...common} field={{ name: 'title', type: 'text', localized: true }} value={{ he: 'שלום', ar: 'مرحبا', 'he-IL': 'ישראל', 'ar-EG': 'مصر', en: 'Hello', 'pt-BR': 'Olá' }} onChange={vi.fn()} defaultLocale="en" locales={['en', 'he', 'ar']} />)
    for (const locale of ['he', 'ar', 'he-IL', 'ar-EG']) {
      const input = screen.getByLabelText(locale)
      expect(input.getAttribute('dir')).toBe('rtl')
      expect(input.getAttribute('lang')).toBe(locale)
    }
    for (const locale of ['en', 'pt-BR']) {
      const input = screen.getByLabelText(locale)
      expect(input.getAttribute('dir')).toBe('ltr')
      expect(input.getAttribute('lang')).toBe(locale)
    }
    const localeCode = screen.getByLabelText('New locale for title')
    fireEvent.change(localeCode, { target: { value: 'ar-SA' } })
    expect(localeCode.getAttribute('dir')).toBe('ltr')
    expect(localeCode.getAttribute('lang')).toBeNull()
  })

  it('passes the locale key into nested text, numbers, and Markdown', () => {
    render(<FieldInput {...common} field={{ name: 'meta', type: 'object', localized: true, fields: [{ name: 'title', type: 'text' }, { name: 'count', type: 'number' }, { name: 'when', type: 'date' }, { name: 'body', type: 'richText' }] }} value={{ he: { title: 'כותרת', count: 2, when: '2026-11-11', body: 'שלום' }, en: { title: 'Title', count: 3, when: '2026-11-12', body: 'Hello' } }} onChange={vi.fn()} />)
    const titles = screen.getAllByLabelText('title')
    expect(titles.map(input => [input.getAttribute('dir'), input.getAttribute('lang')])).toEqual([['rtl', 'he'], ['ltr', 'en']])
    for (const label of ['count', 'when']) {
      const inputs = screen.getAllByLabelText(label)
      expect(inputs.map(input => input.getAttribute('dir'))).toEqual(['ltr', 'ltr'])
      expect(inputs.every(input => input.getAttribute('lang') === null)).toBe(true)
    }
    const visuals = screen.getAllByRole('group', { name: 'body visual editor' })
    expect(visuals.map(group => [group.getAttribute('dir'), group.getAttribute('lang')])).toEqual([['rtl', 'he'], ['ltr', 'en']])
    expect(visuals[0].querySelector('[role="textbox"]')?.getAttribute('dir')).toBe('rtl')
    expect(visuals[0].textContent).toContain('שלום')
    const alts = screen.getAllByLabelText('Image alt text')
    expect(alts.map(input => [input.getAttribute('dir'), input.getAttribute('lang')])).toEqual([['rtl', 'he'], ['ltr', 'en']])
    for (const button of screen.getAllByRole('button', { name: 'Source' })) fireEvent.click(button)
    const bodies = screen.getAllByLabelText<HTMLTextAreaElement>('body')
    expect(bodies.map(input => [input.dir, input.lang])).toEqual([['rtl', 'he'], ['ltr', 'en']])
  })

  it('locks each item in a localized list to that locale key', () => {
    render(<FieldInput {...common} field={{ name: 'lines', type: 'list', localized: true, item: { name: '', type: 'text' } }} value={{ ar: ['مرحبا'], 'fr-CA': ['Bonjour'] }} onChange={vi.fn()} />)
    expect(screen.getByLabelText('ar 1').getAttribute('dir')).toBe('rtl')
    expect(screen.getByLabelText('ar 1').getAttribute('lang')).toBe('ar')
    expect(screen.getByLabelText('fr-CA 1').getAttribute('dir')).toBe('ltr')
    expect(screen.getByLabelText('fr-CA 1').getAttribute('lang')).toBe('fr-CA')
    expect(screen.getByLabelText('New locale for lines').getAttribute('dir')).toBe('ltr')
  })

  it('leaves a text value with no locale key on automatic direction', () => {
    render(<FieldInput {...common} field={{ name: 'title', type: 'text' }} value="שלום" onChange={vi.fn()} />)
    const input = screen.getByLabelText('title')
    expect(input.getAttribute('dir')).toBe('auto')
    expect(input.getAttribute('lang')).toBeNull()
  })

  it('names the modal and handles Escape', () => {
    const close = vi.fn()
    render(<Dialog title="Edit content" open onClose={close}><input aria-label="Title" /></Dialog>)
    expect(screen.getByRole('dialog', { name: 'Edit content' })).toBeTruthy()
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
    expect(close).toHaveBeenCalledOnce()
  })
})
