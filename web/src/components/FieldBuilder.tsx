import { useState } from 'react'
import { Plus } from 'lucide-react'
import { Button } from './ui/button'
import { cn } from '../lib/utils'
import type { ContentType, Field } from '../lib/api'
import { ENUM_RE, FIELD_TYPES, emptyField, metaFor, nameError, switchTemplate } from '../lib/fields'

type EditorProps = {
  field: Field
  name: string
  peers: string[]
  types: ContentType[]
  selfKey?: string
  onPatch: (patch: Partial<Field>) => void
  onRemove: () => void
  onMove: (dir: -1 | 1) => void
}

function FieldEditor({ field, name, peers, types, selfKey, onPatch, onRemove, onMove }: EditorProps) {
  const [optionInput, setOptionInput] = useState('')
  const meta = metaFor(field.type)
  const label = name || 'Unnamed field'
  const nameIssue = nameError(field, peers)
  const targetOptions = types
  const options = field.options || []
  function changeType(type: string) { onPatch(switchTemplate(field, type)) }
  function addOption() {
    const value = optionInput.trim()
    if (!ENUM_RE.test(value) || options.includes(value) || options.length >= 40) { setOptionInput(''); return }
    onPatch({ options: [...options, value] })
    setOptionInput('')
  }
  function patchItem(patch: Partial<Field>) { onPatch({ item: { ...(field.item || emptyField('text')), ...patch } }) }
  return <div className="field-editor">
    <div className="field-editor-head">
      <input aria-label={`Field name ${label}`} placeholder="camelCase name" value={field.name} onChange={e => onPatch({ name: e.target.value })} className={cn(nameIssue && 'is-error')} />
      {nameIssue && <small className="field-issue" role="alert">{nameIssue}</small>}
      <select aria-label={`Type of ${label}`} className="field-type-select" value={field.type} onChange={e => changeType(e.target.value)}>{FIELD_TYPES.map(m => <option key={m.type} value={m.type}>{m.label}</option>)}</select>
      <Button type="button" variant="ghost" aria-label={`Move ${label} up`} onClick={() => onMove(-1)}>↑</Button>
      <Button type="button" variant="ghost" aria-label={`Move ${label} down`} onClick={() => onMove(1)}>↓</Button>
      <Button type="button" variant="ghost" aria-label={`Remove ${label}`} onClick={onRemove}>×</Button>
    </div>
    <p className="field-type-hint">{meta.hint}</p>
    {field.type === 'enum' && <div className="field-config">
      <p>Changing a choice identifier requires reviewing existing content; incompatible values block schema save.</p><p className="config-title">Choices <small>each must be a unique identifier, e.g. news, guide</small></p>
      <div className="field-options">
        {options.map((option, i) => <span className="option-chip" key={i}><input aria-label={`Choice ${i+1} for ${label}`} value={option} onChange={e=>onPatch({options:options.map((old,index)=>index===i?e.target.value:old)})} />{(!ENUM_RE.test(option) || options.filter(value=>value===option).length>1) && <small role="alert">Use a unique identifier beginning with a letter.</small>}<button type="button" aria-label={`Remove choice ${option}`} onClick={() => onPatch({ options: options.filter((_, index) => index !== i) })}>×</button></span>)}
        {options.length < 40 && <input aria-label={`New choice for ${label}`} placeholder="add a choice" value={optionInput} onChange={e => setOptionInput(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addOption() } }} />}
        <Button type="button" variant="outline" disabled={!ENUM_RE.test(optionInput.trim()) || options.includes(optionInput.trim()) || options.length >= 40} onClick={addOption}><Plus size={14} />Add</Button>
      </div>
      {optionInput.trim() && !ENUM_RE.test(optionInput.trim()) && <small className="field-issue" role="alert">Choices must start with a letter (a–z, A–Z, digits, _).</small>}
    </div>}
    {field.type === 'reference' && <div className="field-config">
      <label className="config-label">Target type<select aria-label={`Reference target for ${label}`} value={field.target || ''} onChange={e => onPatch({ target: e.target.value || undefined })}><option value="">Any content type</option>{targetOptions.map(t => <option key={t.key} value={t.key}>{t.name} ({t.key}) · {t.entryCount ?? '?'} entries</option>)}{selfKey && !types.some(t=>t.key===selfKey) && <option value={selfKey}>{selfKey} (this type)</option>}{field.target && field.target!==selfKey && !types.some(t => t.key === field.target) && <option value={field.target}>{field.target} (not in this workspace)</option>}</select></label><p>Self references are allowed. References resolve only within this workspace.</p>{field.target && field.target!==selfKey && !types.some(t=>t.key===field.target) && <small role="alert">Unknown reference target.</small>}{field.target && types.find(t=>t.key===field.target)?.entryCount===0 && <small role="status">This target has no entries yet. Create one before using a required reference.</small>}
    </div>}
    {field.type === 'object' && <div className="field-config">
      <p className="config-title">Sub-fields</p>
      <FieldBuilder value={field.fields || []} types={types} selfKey={selfKey} onChange={next => onPatch({ fields: next })} />
    </div>}
    {field.type === 'list' && <div className="field-config">
      <p className="config-title">Item <small>each repeated entry is one of these</small></p>
      <div className="nested-item"><FieldEditor field={field.item || { name: '', type: 'text' }} name="item" peers={[]} types={types} selfKey={selfKey} onPatch={patchItem} onRemove={() => onPatch({ item: emptyField('text') })} onMove={() => {}} /></div>
    </div>}
    <div className="field-flags">
      <label className="checkbox-label"><input type="checkbox" checked={Boolean(field.required)} onChange={e => onPatch({ required: e.target.checked || undefined })} />Required</label>
      <label className="checkbox-label"><input type="checkbox" checked={Boolean(field.localized)} onChange={e => onPatch({ localized: e.target.checked || undefined })} />Localized</label>
      <label className="checkbox-label"><input type="checkbox" checked={Boolean(field.private)} onChange={e => onPatch({ private: e.target.checked || undefined })} />Private <small>hidden from delivery</small></label>
    </div>
  </div>
}

export function FieldBuilder({ value, onChange, types, selfKey }: { value: Field[]; onChange: (next: Field[]) => void; types: ContentType[]; selfKey?: string }) {
  function patch(index: number, next: Partial<Field>) { onChange(value.map((f, i) => (i === index ? { ...f, ...next } : f))) }
  function remove(index: number) { onChange(value.filter((_, i) => i !== index)) }
  function move(index: number, dir: -1 | 1) { const target = index + dir; if (target < 0 || target >= value.length) return; const next = [...value]; const [item] = next.splice(index, 1); next.splice(target, 0, item); onChange(next) }
  return <div className="field-builder">
    {value.map((field, i) => <FieldEditor key={`${field.name || 'new'}-${i}`} field={field} name={field.name || `Field ${i + 1}`} peers={value.filter((_, j) => j !== i).map(f => f.name)} types={types} selfKey={selfKey} onPatch={next => patch(i, next)} onRemove={() => remove(i)} onMove={dir => move(i, dir)} />)}
    {!value.length && <p className="empty-state">No fields yet. Add your first field below.</p>}
    <Button type="button" variant="outline" disabled={value.length >= 40} onClick={() => onChange([...value, emptyField('text')])}><Plus size={14} />Add field</Button>
  </div>
}
