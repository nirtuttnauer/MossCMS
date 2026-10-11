import type { Field } from './api'
import { LOCALE_PATTERN } from './locales'

// Mirror the server's required rules; empty strings/lists remain valid values.
export function validateEntry(fields: Field[], data: Record<string, unknown>, slug: string): Record<string, string> {
  const errors: Record<string, string> = {}
  if (!slug.trim()) errors.slug = 'Slug is required.'
  else if (!/^[a-z0-9]+(-[a-z0-9]+)*$/.test(slug) || slug.length > 220)
    errors.slug = 'Use lowercase letters, numbers and single hyphens (up to 220 characters).'

  function check(field: Field, value: unknown, path: string) {
    const label = field.label || field.name || 'Field'
    if (value === null || value === undefined) {
      if (field.required) errors[path] = `${label} is required.`
      return
    }
    if (field.localized) {
      if (typeof value !== 'object' || Array.isArray(value) || !Object.keys(value).length || Object.keys(value).some(locale => !LOCALE_PATTERN.test(locale))) {
        errors[path] = `${label} needs at least one valid locale.`
        return
      }
      for (const [locale, translated] of Object.entries(value))
        check({ ...field, localized: false, label: `${label} (${locale})` }, translated, `${path}.${locale}`)
    } else if (field.type === 'object') {
      if (typeof value !== 'object' || Array.isArray(value)) {
        errors[path] = `${label} must be a group of fields.`
        return
      }
      for (const child of field.fields || [])
        check(child, (value as Record<string, unknown>)[child.name], `${path}.${child.name}`)
    } else if (field.type === 'list') {
      if (!Array.isArray(value)) {
        errors[path] = `${label} must be a list.`
        return
      }
      if (field.item) value.forEach((item, i) => check({ ...field.item!, label: `${label} item ${i + 1}` }, item, `${path}[${i}]`))
    }
  }

  for (const field of fields) check(field, data[field.name], `data.${field.name}`)
  return errors
}

export function isEntryValid(fields: Field[], data: Record<string, unknown>, slug: string): boolean {
  return Object.keys(validateEntry(fields, data, slug)).length === 0
}
