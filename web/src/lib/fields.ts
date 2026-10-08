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
  if (field.imageOnly) out.imageOnly = true
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

// Mirrors generated_schema: every field accepts locale, all content fields are nullable.
export function deliveryShape(_definitionName: string, key: string, fields: Field[]): string {
  const scalar:Record<string,string>={text:'String',richText:'String',number:'Float',boolean:'Boolean',date:'Date',reference:'ReferenceNode',asset:'AssetNode'}
  const cap=(value:string)=>value?value[0].toUpperCase()+value.slice(1):''
  const root='Cms'+cap(key || 'type'),sub:string[]=[]
  function valueType(field:Field,name:string):string {
    if(scalar[field.type])return scalar[field.type]
    if(field.type==='list')return `[${valueType(field.item || {name:'',type:'text'},name+'Item')}]`
    if(field.type==='enum'){sub.push(`enum ${name}Enum {\n${(field.options || []).map(o=>'  '+o).join('\n')}\n}`);return name+'Enum'}
    const object=name+'Object';sub.push(objectType(field.fields || [],object));return object
  }
  function objectType(values:Field[],name:string,isRoot=false):string {
    const visible=values.filter(f=>!f.private)
    const lines=visible.map(f=>`  ${f.name}(locale: String! = "en"): ${valueType(f,name+cap(f.name))}`)
    if(!visible.length)lines.push('  empty: Boolean!')
    if(isRoot)lines.push('  id: ID!','  slug: String!')
    return `type ${name} {\n${lines.join('\n')}\n}`
  }
  const main=objectType(fields,root,true)
  return `${main}\n\n${sub.join('\n\n')}\n\nextend type ProjectQuery {\n  all${root}(first: Int! = 20, after: String = null, locale: String! = "en"): [${root}!]!\n}\n\n# ReferenceNode and AssetNode are shared API types.`
}

export function hiddenFieldCount(fields:Field[]):number {
  return fields.reduce((sum,f)=>sum+(f.private?1:0)+hiddenFieldCount(f.fields || [])+(f.item?hiddenFieldCount([f.item]):0),0)
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

export type FieldDiff = {path:string;before?:Field;after?:Field;kind:'added'|'removed'|'changed'}
export function fieldDiff(before:Field[],after:Field[],prefix=''):FieldDiff[] {
  const diffs:FieldDiff[]=[]
  for(const name of new Set([...before,...after].map(f=>f.name))){
    const old=before.find(f=>f.name===name),next=after.find(f=>f.name===name),path=prefix+name
    if(!old || !next){diffs.push({path,before:old,after:next,kind:old?'removed':'added'});continue}
    const shallow=(f:Field)=>({...clean(f,true),fields:undefined,item:undefined})
    if(JSON.stringify(shallow(old))!==JSON.stringify(shallow(next)))diffs.push({path,before:old,after:next,kind:'changed'})
    if(old.type==='object' && next.type==='object')diffs.push(...fieldDiff(old.fields || [],next.fields || [],path+'.'))
    if(old.type==='list' && next.type==='list' && old.item && next.item)diffs.push(...fieldDiff([{...old.item,name:'item'}],[{...next.item,name:'item'}],path+'[].'))
  }
  return diffs
}
export function migrationSuggestion(before:Field[],after:Field[],rename:Record<string,string>={}) {
  const removed=before.filter(f=>!after.some(n=>n.name===f.name)),added=after.filter(f=>!before.some(n=>n.name===f.name))
  const chosen=Object.fromEntries(Object.entries(rename).filter(([old,next])=>removed.some(f=>f.name===old) && added.some(f=>f.name===next)))
  const defaults:Record<string,unknown>={}
  for(const field of added.filter(f=>f.required && !Object.values(chosen).includes(f.name)))defaults[field.name]=field.type==='boolean'?false:field.type==='number'?0:field.type==='list'?[]:null
  return {rename:chosen,defaults,drop:removed.filter(f=>!chosen[f.name]).map(f=>f.name)}
}
