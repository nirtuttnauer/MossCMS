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

it('explains invalid and duplicate inline enum edits',()=>{
  render(<FieldBuilder value={[{name:'choices',type:'enum',options:['One','One','bad choice']}]} types={[]} onChange={vi.fn()} />)
  expect(screen.getAllByRole('alert')).toHaveLength(3)
  expect(screen.getByLabelText('Choice 1 for choices')).toBeTruthy()
})
