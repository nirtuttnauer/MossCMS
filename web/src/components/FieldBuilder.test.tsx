import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { FieldBuilder } from './FieldBuilder'
import { emptyField, shapeSignature, switchTemplate, toSchema, validateSchema, type Field } from '../lib/fields'
import type { ContentType } from '../lib/api'

afterEach(cleanup)

const types: ContentType[] = [{ id: '1', key: 'person', name: 'Person', fields: [], version: 1 }]
const noTypes: ContentType[] = []

describe('field schema logic', () => {
  it('builds a clean schema, dropping empty names and unset flags', () => {
    const schema = toSchema([{ name: 'title', type: 'text', required: true }, { name: '', type: 'boolean' }])
    expect(schema).toEqual([{ name: 'title', type: 'text', required: true }, { type: 'boolean' }])
  })
  it('flags reserved, duplicate, and empty object names', () => {
    expect(validateSchema([{ name: 'slug', type: 'text' }]).some(e => /reserved/.test(e))).toBe(true)
    expect(validateSchema([{ name: 'a', type: 'text' }, { name: 'a', type: 'text' }]).some(e => /already used/.test(e))).toBe(true)
    expect(validateSchema([{ name: 'group', type: 'object', fields: [] }]).some(e => /at least one sub-field/.test(e))).toBe(true)
  })
  it('validates enum options', () => {
    expect(validateSchema([{ name: 'cat', type: 'enum', options: ['news', 'news'] }]).some(e => /unique/.test(e))).toBe(true)
    expect(validateSchema([{ name: 'cat', type: 'enum', options: ['9bad'] }]).some(e => /letter/.test(e))).toBe(true)
    expect(validateSchema([{ name: 'cat', type: 'enum', options: ['news'] }])).toEqual([])
  })
  it('switching a field type resets its config but keeps identity and flags', () => {
    const from: Field = { name: 'x', type: 'enum', options: ['a', 'b'], required: true, private: true }
    const to = switchTemplate(from, 'object')
    expect(to).toEqual({ name: 'x', type: 'object', required: true, private: true, fields: [] })
  })
  it('emptyField gives a sane default per type', () => {
    expect(emptyField('enum')).toEqual({ name: '', type: 'enum', options: [] })
    expect(emptyField('list')).toEqual({ name: '', type: 'list', item: { name: '', type: 'text' } })
    expect(emptyField('text')).toEqual({ name: '', type: 'text' })
  })
  it('shapeSignature reflects structure but not flags', () => {
    const base: Field[] = [{ name: 'title', type: 'text' }]
    expect(shapeSignature(base)).toBe(shapeSignature([{ name: 'title', type: 'text', required: true, private: true }]))
    expect(shapeSignature([{ name: 'title', type: 'richText' }])).not.toBe(shapeSignature(base))
    expect(shapeSignature([{ name: 'title', type: 'text' }, { name: 'body', type: 'text' }])).not.toBe(shapeSignature(base))
  })
})

describe('FieldBuilder interactions', () => {
  it('adds a text field and edits its name', () => {
    const change = vi.fn()
    render(<FieldBuilder value={[]} onChange={change} types={noTypes} />)
    fireEvent.click(screen.getByRole('button', { name: 'Add field' }))
    expect(change).toHaveBeenLastCalledWith([{ name: '', type: 'text' }])
    const value: Field[] = [{ name: '', type: 'text' }]
    render(<FieldBuilder value={value} onChange={change} types={noTypes} />)
    fireEvent.change(screen.getByLabelText(/Field name/), { target: { value: 'title' } })
    expect(change).toHaveBeenLastCalledWith([{ name: 'title', type: 'text' }])
  })
  it('shows reference targets with counts and permits self references', () => {
    render(<FieldBuilder value={[{ name: 'author', type: 'reference' }]} onChange={vi.fn()} types={types} />)
    const target = screen.getByLabelText('Reference target for author') as HTMLSelectElement
    expect(Array.from(target.options).map(option => option.value)).toEqual(['', 'person'])
    expect(screen.getByRole('option', { name: /Person \(person\)/ })).toBeTruthy()
  })
  it('adds an enum choice', () => {
    const change = vi.fn()
    render(<FieldBuilder value={[{ name: 'cat', type: 'enum', options: [] }]} onChange={change} types={noTypes} />)
    fireEvent.change(screen.getByLabelText('New choice for cat'), { target: { value: 'news' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    expect(change).toHaveBeenLastCalledWith([{ name: 'cat', type: 'enum', options: ['news'] }])
  })
})

it('explains invalid and duplicate inline enum edits', () => {
  render(<FieldBuilder value={[{ name: 'choices', type: 'enum', options: ['One', 'One', 'bad choice'] }]} types={[]} onChange={vi.fn()} />)
  expect(screen.getAllByRole('alert')).toHaveLength(3)
  expect(screen.getByLabelText('Choice 1 for choices')).toBeTruthy()
})

it('outline opens nested cards and arrow reorder retains complete field settings', () => {
  const change = vi.fn()
  const first: Field = { name: 'group', type: 'object', fields: [{ name: 'child', type: 'enum', options: ['One'], private: true }] }
  const second: Field = { name: 'title', type: 'text', required: true }
  render(<FieldBuilder value={[first, second]} onChange={change} types={[]} />)
  const child = screen.getByLabelText('Field name child').closest('details')!
  child.open = false
  fireEvent.click(screen.getByText('Schema outline'))
  fireEvent.click(screen.getByRole('button', { name: 'child · enum' }))
  expect(child.open).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: 'Move group down' }))
  expect(change).toHaveBeenLastCalledWith([second, first])
  expect(screen.getAllByRole('status')[0].textContent).toContain('position 2')
})

it('keeps unfinished enum choices with their fields after reorder and removal', () => {
  const change = vi.fn()
  const first: Field = { name: 'first', type: 'enum', options: ['One'] }
  const second: Field = { name: 'second', type: 'enum', options: ['Two'] }
  const { rerender } = render(<FieldBuilder value={[first, second]} onChange={change} types={noTypes} />)
  const firstInput = screen.getByLabelText('New choice for first') as HTMLInputElement
  const secondInput = screen.getByLabelText('New choice for second') as HTMLInputElement
  fireEvent.change(firstInput, { target: { value: 'FirstDraft' } })
  fireEvent.change(secondInput, { target: { value: 'SecondDraft' } })

  fireEvent.click(screen.getByRole('button', { name: 'Move first down' }))
  expect(change).toHaveBeenLastCalledWith([second, first])
  rerender(<FieldBuilder value={[second, first]} onChange={change} types={noTypes} />)
  expect(screen.getByLabelText('New choice for first')).toBe(firstInput)
  expect(firstInput.value).toBe('FirstDraft')
  expect(screen.getByLabelText('New choice for second')).toBe(secondInput)
  expect(secondInput.value).toBe('SecondDraft')

  fireEvent.click(screen.getByRole('button', { name: 'Remove second' }))
  expect(change).toHaveBeenLastCalledWith([first])
  rerender(<FieldBuilder value={[first]} onChange={change} types={noTypes} />)
  expect(screen.getByLabelText('New choice for first')).toBe(firstInput)
  expect(firstInput.value).toBe('FirstDraft')
  fireEvent.keyDown(firstInput, { key: 'Enter' })
  expect(change).toHaveBeenLastCalledWith([{ ...first, options: ['One', 'FirstDraft'] }])
})

it('does not reorder or announce moves beyond either end', () => {
  const change = vi.fn()
  render(<FieldBuilder value={[{ name: 'first', type: 'text' }, { name: 'last', type: 'text' }]} onChange={change} types={noTypes} />)
  fireEvent.click(screen.getByRole('button', { name: 'Move first up' }))
  fireEvent.click(screen.getByRole('button', { name: 'Move last down' }))
  expect(change).not.toHaveBeenCalled()
  expect(screen.getByRole('status').textContent).toBe('')
})

it('follows list item outline paths and opens every nested ancestor', () => {
  const change = vi.fn()
  const value: Field[] = [{
    name: 'group',
    type: 'object',
    fields: [{
      name: 'items',
      type: 'list',
      item: { name: '', type: 'object', fields: [{ name: 'choice', type: 'enum', options: ['One'] }] },
    }],
  }]
  const { container } = render(<FieldBuilder value={value} onChange={change} types={noTypes} rootId="schema" />)
  const cards = ['schema-0', 'schema-0.0', 'schema-0.0.item', 'schema-0.0.item.0'].map(id => {
    const card = container.querySelector<HTMLDetailsElement>(`[id="${id}"]`)!
    card.open = false
    return card
  })
  const child = cards[3]
  child.scrollIntoView = vi.fn()
  const focus = vi.spyOn(child.querySelector('summary')!, 'focus')
  fireEvent.click(screen.getByText('Schema outline'))
  fireEvent.click(screen.getByRole('button', { name: 'choice · enum' }))
  expect(cards.every(card => card.open)).toBe(true)
  expect(child.scrollIntoView).toHaveBeenCalledWith({ block: 'center' })
  expect(focus).toHaveBeenCalledOnce()
  fireEvent.change(screen.getByLabelText('Choice 1 for choice'), { target: { value: 'Two' } })
  expect(change).toHaveBeenLastCalledWith([{
    ...value[0],
    fields: [{ ...value[0].fields![0], item: { name: '', type: 'object', fields: [{ name: 'choice', type: 'enum', options: ['Two'] }] } }],
  }])
})

it('allows the fortieth enum choice and then disables additions', () => {
  const change = vi.fn()
  const field: Field = { name: 'choices', type: 'enum', options: Array.from({ length: 39 }, (_, i) => `Option${i}`) }
  const { rerender } = render(<FieldBuilder value={[field]} onChange={change} types={noTypes} />)
  const input = screen.getByLabelText('New choice for choices')
  fireEvent.change(input, { target: { value: 'Last' } })
  fireEvent.keyDown(input, { key: 'Enter' })
  const full: Field = { ...field, options: [...field.options!, 'Last'] }
  expect(change).toHaveBeenLastCalledWith([full])
  rerender(<FieldBuilder value={[full]} onChange={change} types={noTypes} />)
  expect(screen.queryByLabelText('New choice for choices')).toBeNull()
  expect((screen.getByRole('button', { name: 'Add' }) as HTMLButtonElement).disabled).toBe(true)
  change.mockClear()
  fireEvent.click(screen.getByRole('button', { name: 'Add' }))
  expect(change).not.toHaveBeenCalled()
})

it('allows the fortieth field and then disables adding and duplicating', () => {
  const change = vi.fn()
  const fields: Field[] = Array.from({ length: 39 }, (_, i) => ({ name: `field${i}`, type: 'text' }))
  const { rerender } = render(<FieldBuilder value={fields} onChange={change} types={noTypes} />)
  fireEvent.click(screen.getByRole('button', { name: 'Duplicate field38' }))
  const full: Field[] = [...fields, { name: 'field38Copy', type: 'text' }]
  expect(change).toHaveBeenLastCalledWith(full)
  rerender(<FieldBuilder value={full} onChange={change} types={noTypes} />)
  expect((screen.getByRole('button', { name: 'Add field' }) as HTMLButtonElement).disabled).toBe(true)
  expect(screen.queryByRole('button', { name: /^Duplicate / })).toBeNull()
  change.mockClear()
  fireEvent.click(screen.getByRole('button', { name: 'Add field' }))
  expect(change).not.toHaveBeenCalled()
})
