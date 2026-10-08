import { useState } from 'react'
import { Button } from './ui/button'
import type { Asset, Entry, Field } from '../lib/api'

type Props = { field: Field; value: unknown; onChange: (value: unknown) => void; references: Entry[]; assets: Asset[] }
export function FieldInput({ field, value, onChange, references, assets }: Props) {
  const [newLocale, setNewLocale] = useState('')
  const label = field.label || field.name || 'Item'
  const object = (value && typeof value === 'object' && !Array.isArray(value) ? value : {}) as Record<string, unknown>
  if (field.localized) return <fieldset className="field-group"><legend>{label}{field.required ? ' *' : ''}</legend>{Object.entries(object).map(([locale, translation]) => <div key={locale} className="locale-field"><FieldInput field={{ ...field, localized: false, label: locale }} value={translation} onChange={next => onChange({ ...object, [locale]: next })} references={references} assets={assets} /><button type="button" aria-label={`Remove ${locale} translation`} onClick={() => { const next = { ...object }; delete next[locale]; onChange(next) }}>×</button></div>)}<div className="inline-form"><input aria-label={`New locale for ${label}`} placeholder="en, fr, he…" value={newLocale} onChange={e => setNewLocale(e.target.value)} /><Button type="button" variant="outline" onClick={() => { if (/^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$/.test(newLocale)) { onChange({ ...object, [newLocale]: object[newLocale] ?? '' }); setNewLocale('') } }}>Add locale</Button></div></fieldset>
  if (field.type === 'object') return <fieldset className="field-group"><legend>{label}</legend>{field.fields?.map(child => <FieldInput key={child.name} field={child} value={object[child.name]} onChange={next => onChange({ ...object, [child.name]: next })} references={references} assets={assets} />)}</fieldset>
  if (field.type === 'list') {
    const items = Array.isArray(value) ? value : []
    return <fieldset className="field-group"><legend>{label}</legend>{items.map((item, i) => <div className="list-item" key={i}><FieldInput field={{ ...field.item!, name: `${label} ${i + 1}` }} value={item} onChange={next => onChange(items.map((old, index) => index === i ? next : old))} references={references} assets={assets} /><button type="button" aria-label={`Remove ${label} item ${i + 1}`} onClick={() => onChange(items.filter((_, index) => i !== index))}>×</button></div>)}<Button type="button" variant="outline" onClick={() => onChange([...items, null])}>Add item</Button></fieldset>
  }
  if (field.type === 'boolean') return <label className="checkbox-label"><input type="checkbox" checked={value === true} onChange={e => onChange(e.target.checked)} />{label}{field.required ? ' *' : ''}</label>
  if (field.type === 'richText') return <label>{label}{field.required ? ' *' : ''}<textarea rows={6} value={String(value ?? '')} required={field.required} onChange={e => onChange(e.target.value)} /></label>
  if (['enum', 'reference', 'asset'].includes(field.type)) {
    const options = field.type === 'enum' ? field.options?.map(v => ({ id: v, name: v })) : field.type === 'asset' ? assets : references.filter(e => !field.target || e.typeKey === field.target).map(e => ({ id: e.id, name: `${e.title} (${e.typeKey})` }))
    return <label>{label}{field.required ? ' *' : ''}<select value={String(value ?? '')} required={field.required} onChange={e => onChange(e.target.value || null)}><option value="">Select…</option>{options?.map(option => <option key={option.id} value={option.id}>{option.name}</option>)}</select></label>
  }
  return <label>{label}{field.required ? ' *' : ''}<input type={field.type === 'number' ? 'number' : field.type === 'date' ? 'date' : 'text'} step={field.type === 'number' ? 'any' : undefined} required={field.required} value={String(value ?? '')} onChange={e => onChange(field.type === 'number' ? e.target.value === '' ? null : Number(e.target.value) : e.target.value)} /></label>
}
