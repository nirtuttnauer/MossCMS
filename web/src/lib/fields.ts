import type { Field } from './api'

export type { Field }

export type FieldTypeMeta = { type: string; label: string; hint: string; config?: 'options' | 'target' | 'object' | 'item' }

export const FIELD_TYPES: FieldTypeMeta[] = [
  { type: 'text', label: 'Text', hint: 'A short single-line string.' },
  { type: 'richText', label: 'Rich text', hint: 'Longer prose (stored as text).' },
  { type: 'number', label: 'Number', hint: 'Whole or decimal value.' },
  { type: 'boolean', label: 'Checkbox', hint: 'True or false.' },
  { type: 'date', label: 'Date', hint: 'Calendar date, YYYY-MM-DD.' },
  { type: 'enum', label: 'Choices', hint: 'Pick from a fixed list of values.', config: 'options' },
  { type: 'reference', label: 'Reference', hint: 'Point at an entry of another type.', config: 'target' },
  { type: 'asset', label: 'Media', hint: 'An uploaded file from Assets.' },
  { type: 'object', label: 'Group', hint: 'A named set of sub-fields.', config: 'object' },
  { type: 'list', label: 'Repeater', hint: 'A repeatable collection of items.', config: 'item' },
]

export function metaFor(type: string): FieldTypeMeta {
  return FIELD_TYPES.find(m => m.type === type) || FIELD_TYPES[0]
}

export const NAME_RE = /^[a-z][a-zA-Z0-9_]{0,59}$/
export const ENUM_RE = /^[A-Za-z][A-Za-z0-9_]{0,50}$/
export const RESERVED = new Set(['id', 'slug', 'status', 'version', 'updatedAt', '_data'])

export function emptyField(type: string): Field {
  const field: Field = { name: '', type }
  if (type === 'enum') field.options = []
  if (type === 'object') field.fields = []
  if (type === 'list') field.item = { name: '', type: 'text' }
  if (type === 'reference') field.target = ''
  return field
}

// Keep a field's identity + flags but reset the type-specific config when the type changes.
export function switchTemplate(field: Field, type: string): Field {
  const fresh = emptyField(type)
  return { ...fresh, name: field.name, required: field.required, localized: field.localized, private: field.private, ...(type === 'reference' && field.target ? { target: field.target } : {}) }
}

// Strip empties so the saved schema is clean and matches what the backend expects.
export function clean(field: Field, named: boolean): Field {
  const out: Partial<Field> = {}
  if (named && field.name) out.name = field.name
  out.type = field.type
  if (field.label) out.label = field.label
  if (field.required) out.required = true
  if (field.localized) out.localized = true
  if (field.private) out.private = true
  if (field.type === 'enum') out.options = field.options || []
  if (field.type === 'reference' && field.target) out.target = field.target
  if (field.type === 'object') out.fields = (field.fields || []).map(f => clean(f, true))
  if (field.type === 'list') out.item = clean(field.item || { name: '', type: 'text' }, false)
  return out as Field
}

export function toSchema(fields: Field[]): Field[] {
  return fields.map(f => clean(f, true))
}

// A fingerprint of the *form shape* only (names, types, localized, options, targets, nesting).
// It ignores required/private/label so toggling those flags doesn't reset a preview's values.
export function shapeSignature(fields: Field[]): string {
  const strip = (f: Field, named: boolean): Record<string, unknown> => ({
    n: named ? f.name : undefined,
    t: f.type,
    l: f.localized ? true : undefined,
    o: f.type === 'enum' ? [...(f.options || [])].sort() : undefined,
    x: f.type === 'reference' ? f.target : undefined,
    f: f.type === 'object' ? (f.fields || []).map(c => strip(c, true)) : undefined,
    i: f.type === 'list' ? strip(f.item || { name: '', type: 'text' }, false) : undefined,
  })
  return JSON.stringify(fields.map(f => strip(f, true)))
}

// Render the delivery GraphQL shape for a content type, mirroring the backend's generated schema:
// a `Cms<Key>` type with id/slug plus non-private fields; enums as <Name>Enum, nested objects as
// <Name>Object; localized fields take a `locale` argument; references/assets resolve to nodes.
export function deliveryShape(definitionName: string, key: string, fields: Field[]): string {
  const scalar: Record<string, string> = { text: 'String', richText: 'String', number: 'Float', boolean: 'Boolean', date: 'Date' }
  const type = key ? `Cms${key[0].toUpperCase()}${key.slice(1)}` : 'CmsType'
  const sub: string[] = []
  const cap = (n: string) => n ? n[0].toUpperCase() + n.slice(1) : ''
  function ref(f: Field, base: string): string {
    const kind = f.type
    const b = `${base}${cap(f.name || 'Item')}`
    const loc = f.localized ? '($locale: String = "en")' : ''
    if (kind in scalar) return `${f.name}: ${scalar[kind]}${loc}`
    if (kind === 'enum') {
      const options = f.options || []
      sub.push(`enum ${b}Enum {\n${options.map(o => `  ${o}\n`).join('')}}`)
      return `${f.name}: ${b}Enum${loc}`
    }
    if (kind === 'object') {
      const inner = (f.fields || []).filter(c => !c.private).map(c => `  ${ref(c, b)}`).join('\n')
      sub.push(`type ${b}Object {\n${inner || '  empty: Boolean\n'}}`)
      return `${f.name}: ${b}Object${loc}`
    }
    if (kind === 'list') return `${f.name}: [${ref(f.item || { name: '', type: 'text' }, b)}]${loc}`
    if (kind === 'reference') return `${f.name}: CmsReference`
    if (kind === 'asset') return `${f.name}: CmsAsset`
    return `${f.name}: String${loc}`
  }
  const body = ['  id: ID', '  slug: String', ...fields.filter(f => !f.private).map(f => `  ${ref(f, type)}`)].join('\n')
  return `type ${type} {\n${body}\n}\n\n${sub.join('\n\n')}`.trim()
}

type CheckCtx = { errors: string[] }

function checkLevel(fields: Field[], path: string, depth: number, named: boolean, ctx: CheckCtx) {
  if (depth > 5) { ctx.errors.push(`${path}: nesting is limited to five levels.`); return }
  if (!Array.isArray(fields) || fields.length < 1 || fields.length > 40) { ctx.errors.push(`${path}: needs 1–40 fields.`); return }
  const seen = new Set<string>()
  fields.forEach((f, i) => {
    const label = named ? (f.name ? f.name : `field ${i + 1}`) : `${path} item`
    if (!f.type || !FIELD_TYPES.some(m => m.type === f.type)) { ctx.errors.push(`${label}: choose a field type.`); return }
    if (named) {
      const name = f.name || ''
      if (!NAME_RE.test(name)) ctx.errors.push(`${label}: name must start with a letter, then letters, digits, or _ (max 60).`)
      else if (RESERVED.has(name)) ctx.errors.push(`${label}: "${name}" is reserved by the system.`)
      else if (seen.has(name)) ctx.errors.push(`${label}: "${name}" is already used at this level.`)
      else seen.add(name)
    }
    if (f.type === 'object') {
      if (!f.fields || !f.fields.length) ctx.errors.push(`${label}: add at least one sub-field.`)
      else checkLevel(f.fields, `${label} group`, depth + 1, true, ctx)
    }
    if (f.type === 'list') {
      checkLevel([f.item || { name: '', type: '' }], `${label} repeater`, depth + 1, false, ctx)
    }
    if (f.type === 'enum') {
      const options = f.options || []
      if (!options.length) ctx.errors.push(`${label}: add at least one choice.`)
      else if (options.length > 40) ctx.errors.push(`${label}: allow at most 40 choices.`)
      else if (new Set(options).size !== options.length) ctx.errors.push(`${label}: choices must be unique.`)
      else {
        const invalid = options.filter(o => !ENUM_RE.test(o))
        if (invalid.length) ctx.errors.push(`${label}: choices must start with a letter (a–z, A–Z, digits, _). Problem: ${invalid.join(', ')}.`)
      }
    }
  })
}

export function validateSchema(fields: Field[]): string[] {
  const ctx: CheckCtx = { errors: [] }
  checkLevel(fields, 'Fields', 0, true, ctx)
  return ctx.errors
}

export function nameError(field: Field, peers: string[]): string {
  if (!field.name) return ''
  if (!NAME_RE.test(field.name)) return 'Start with a letter; letters, digits, or _ only (max 60).'
  if (RESERVED.has(field.name)) return `"${field.name}" is reserved by the system.`
  if (peers.includes(field.name)) return 'Already used at this level.'
  return ''
}
