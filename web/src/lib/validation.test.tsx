import { describe, expect, it } from 'vitest'
import { isEntryValid, validateEntry } from './validation'
import type { Field } from './api'

describe('validation', () => {
  const fields: Field[] = [
    { name: 'title', type: 'text', required: true },
    { name: 'count', type: 'number', required: true },
    { name: 'enabled', type: 'boolean', required: true },
    {
      name: 'author',
      type: 'object',
      required: true,
      fields: [
        { name: 'name', type: 'text', required: true },
        { name: 'bio', type: 'text', required: false },
      ],
    },
    {
      name: 'tags',
      type: 'list',
      required: true,
      item: { name: 'tag', type: 'text', required: true },
    },
    {
      name: 'localized_title',
      type: 'text',
      required: true,
      localized: true,
    },
  ]

  it('preserves valid 0 and false as non-missing for required fields', () => {
    const data = {
      title: 'Post 1',
      count: 0,
      enabled: false,
      author: { name: 'Alice', bio: '' },
      tags: ['cool'],
      localized_title: { en: 'English title' },
    }
    const errors = validateEntry(fields, data, 'post-1')
    expect(errors).toEqual({})
    expect(isEntryValid(fields, data, 'post-1')).toBe(true)
  })

  it('accepts server-valid empty scalar/list values', () => {
    expect(validateEntry([{ name: 'title', type: 'text', required: true }, { name: 'tags', type: 'list', required: true, item: { name: '', type: 'text' } }], { title: '', tags: [] }, 'valid')).toEqual({})
  })

  it('flags missing required fields including nested objects and localized fields', () => {
    const data = {
      title: null,
      count: undefined,
      enabled: null,
      author: { name: null },
      tags: null,
      localized_title: {},
    }
    const errors = validateEntry(fields, data, '')
    expect(errors['slug']).toBe('Slug is required.')
    expect(errors['data.title']).toBe('title is required.')
    expect(errors['data.count']).toBe('count is required.')
    expect(errors['data.enabled']).toBe('enabled is required.')
    expect(errors['data.author.name']).toBe('name is required.')
    expect(errors['data.tags']).toBe('tags is required.')
    expect(errors['data.localized_title']).toBe('localized_title needs at least one valid locale.')
    expect(isEntryValid(fields, data, '')).toBe(false)
  })

  it('flags null items in lists with required item fields', () => {
    const listFields: Field[] = [
      {
        name: 'items',
        type: 'list',
        item: { name: 'item', type: 'text', required: true },
      },
    ]
    const data = {
      items: ['Valid item', null, undefined],
    }
    const errors = validateEntry(listFields, data, 'test')
    expect(errors['data.items[1]']).toBe('items item 2 is required.')
    expect(errors['data.items[2]']).toBe('items item 3 is required.')
  })
})
