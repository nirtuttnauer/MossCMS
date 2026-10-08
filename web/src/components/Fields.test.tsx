import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { FieldInput } from './Fields'
import { Dialog } from './ui/dialog'

afterEach(cleanup)
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
  it('filters reference options to the declared target type', () => {
    const references = [{ id: 'a', typeKey: 'person', title: 'Author' }, { id: 'b', typeKey: 'article', title: 'Article' }] as Parameters<typeof FieldInput>[0]['references']
    render(<FieldInput {...common} references={references} field={{ name: 'author', type: 'reference', target: 'person' }} value="" onChange={vi.fn()} />)
    expect(screen.getByRole('option', { name: 'Author (person)' })).toBeTruthy()
    expect(screen.queryByRole('option', { name: 'Article (article)' })).toBeNull()
  })
  it('names the modal and handles Escape', () => {
    const close = vi.fn()
    render(<Dialog title="Edit content" open onClose={close}><input aria-label="Title" /></Dialog>)
    expect(screen.getByRole('dialog', { name: 'Edit content' })).toBeTruthy()
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
    expect(close).toHaveBeenCalledOnce()
  })
})
