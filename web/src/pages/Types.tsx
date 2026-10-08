import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useUnsavedChanges } from '../lib/unsaved'
import { Blocks, Plus } from 'lucide-react'
import { Button } from '../components/ui/button'
import { Dialog } from '../components/ui/dialog'
import { FieldBuilder } from '../components/FieldBuilder'
import { FieldInput } from '../components/Fields'
import { initialData } from './Content'
import { shapeSignature, toSchema, validateSchema, deliveryShape, hiddenFieldCount, fieldDiff, migrationSuggestion } from '../lib/fields'
import { gql, message, typeFields, type Asset, type ContentType, type Entry, type Field } from '../lib/api'

const defaultFields: Field[] = [
  { name: 'title', type: 'text', required: true },
  { name: 'body', type: 'richText' },
]

function TypeEditor({ definition, types, onClose, onSaved }: { definition: ContentType | null; types: ContentType[]; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState(definition?.name || '')
  const [key, setKey] = useState(definition?.key || '')
  const [fields, setFields] = useState<Field[]>(definition?.fields || defaultFields)
  const [rename,setRename]=useState<Record<string,string>>({})
  const [migration, setMigration] = useState('{}')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [history, setHistory] = useState<unknown>(null)
  const [showJson, setShowJson] = useState(false)
  const [tab, setTab] = useState<'form' | 'schema'>('form')
  const [previewData, setPreviewData] = useState<Record<string, unknown>>(() => initialData(definition?.fields || defaultFields))
  const [references, setReferences] = useState<Entry[]>([])
  const [assets, setAssets] = useState<Asset[]>([])
  const fingerprint = JSON.stringify({name, key, fields, migration})
  const initialFingerprint = useRef(fingerprint)
  const confirmClose = useUnsavedChanges(busy || fingerprint !== initialFingerprint.current)
  const close = () => { if (!busy && confirmClose()) onClose() }
  const signature = shapeSignature(fields)
  const lastSignature = useRef(signature)
  const issues = validateSchema(fields,[...types.map(t=>t.key),key])
  const diffs=definition?fieldDiff(definition.fields,fields):[]
  const suggestion=definition?migrationSuggestion(definition.fields,fields,rename):{}
  const invalid = !definition && key !== '' && !/^[a-z][a-zA-Z0-9_]*$/.test(key)
  useEffect(() => {
    gql<{ entries: { nodes: Entry[] }; assets: Asset[] }>(`{entries(first:100){nodes{id typeKey slug title data status version updatedAt}} assets(first:100){id name mime size url}}`).then(result => { setReferences(result.entries.nodes); setAssets(result.assets) }).catch(() => {})
  }, [])
  useEffect(() => {
    if (lastSignature.current !== signature) { lastSignature.current = signature; setPreviewData(initialData(fields)) }
  }, [signature])
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError('')
    try {
      await gql(`mutation($key:String!,$name:String!,$fields:JSON!,$version:Int,$migration:JSON){saveContentType(key:$key,name:$name,fields:$fields,version:$version,migration:$migration){${typeFields}}}`, { key, name, fields: toSchema(fields), version: definition?.version, migration: JSON.parse(migration) })
      onSaved()
    } catch (reason) { setError(message(reason)) }
    finally { setBusy(false) }
  }
  async function loadHistory() {
    try { const result = await gql<{ schemaHistory: unknown }>('query($key:String!){schemaHistory(key:$key)}', { key: definition!.key }); setHistory(result.schemaHistory) }
    catch (reason) { setError(message(reason)) }
  }
  const previewKey = key ? `allCms${key[0].toUpperCase()}${key.slice(1)}` : ''
  return <Dialog wide title={definition ? `Edit ${definition.name}` : 'New content type'} open onClose={close}><div className="editor-layout">
    <form className="editor-form" onSubmit={submit}>
      <div className="type-identity">
        <label>Name<input required maxLength={100} value={name} onChange={e => setName(e.target.value)} placeholder="Article" /></label>
        <label>Key<input required pattern="[a-z][a-zA-Z0-9_]*" readOnly={Boolean(definition)} value={key} onChange={e => setKey(e.target.value)} placeholder="article" className={invalid ? 'is-error' : undefined} />{invalid && <small className="field-issue" role="alert">Start with a letter; letters, digits, or _ only.</small>}</label>
        {previewKey && <small>Exposes <code style={{backgroundColor: 'var(--muted-foreground)', padding: '2px 4px', borderRadius: '4px'}}>{previewKey}</code> in the delivery GraphQL API.</small>}
      </div>
      <div className="type-builder">
        <div className="section-head">
          <h2 style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>Fields <Button type="button" variant="ghost" onClick={() => setShowJson(v => !v)}>{showJson ? 'Hide JSON' : 'View JSON'}</Button></h2>
        </div>
        <FieldBuilder value={fields} types={types} selfKey={key} onChange={setFields} />
        {showJson && <pre className="schema-json" aria-label="Schema JSON" style={{backgroundColor: 'var(--card)', padding: '1rem', borderRadius: '8px', overflowX: 'auto', fontSize: '0.8rem'}}>{JSON.stringify(toSchema(fields), null, 2)}</pre>}
        {issues.length > 0 && <div className="schema-issues" role="alert" style={{marginTop: '1rem', color: 'var(--error)'}}><ul style={{listStyle: 'none', padding: 0}}>{issues.map((issue, i) => <li key={i} style={{marginBottom: '4px'}}>• {issue}</li>)}</ul></div>}
      </div>
      {definition && <><section><h3>Schema changes</h3>{diffs.length?<ul>{diffs.map(diff=><li key={diff.path}><strong>{diff.path}: {diff.kind}</strong><details><summary>Before / after</summary><pre>{JSON.stringify({before:diff.before || null,after:diff.after || null},null,2)}</pre></details></li>)}</ul>:<p>No field changes.</p>}{definition.fields.filter(old=>!fields.some(f=>f.name===old.name)).map(old=><label key={old.name}>Rename {old.name} to<select value={rename[old.name] || ''} onChange={e=>setRename(r=>({...r,[old.name]:e.target.value}))}><option value="">No rename selected</option>{fields.filter(f=>!definition.fields.some(previous=>previous.name===f.name)).map(f=><option key={f.name} value={f.name}>{f.name}</option>)}</select></label>)}<p>Suggested drops remove stored values. Defaults are placeholders for missing keys; replace nulls with valid values. Changed/nested fields need a manually reviewed migration. No suggestion is applied automatically.</p><pre>{JSON.stringify(suggestion,null,2)}</pre><Button type="button" variant="outline" onClick={()=>{if(migration.trim()==='{}' || window.confirm('Replace your edited migration with this suggestion?'))setMigration(JSON.stringify(suggestion,null,2))}}>Use suggested migration</Button></section><label>Migration for existing entries<textarea className="code-input" aria-label="Schema migration" rows={4} value={migration} onChange={e => setMigration(e.target.value)} /></label><small>Rename, supply defaults, or explicitly drop values. Example: {'{"rename":{"old":"new"},"defaults":{"featured":false},"drop":["obsolete"]}'}. Every entry must validate before the schema is saved.</small><Button type="button" variant="outline" onClick={loadHistory}>Schema history · version {definition.version}</Button>{history !== null && <pre className="schema-json" style={{backgroundColor: 'var(--card)', padding: '1rem', borderRadius: '8px', overflowX: 'auto', fontSize: '0.8rem'}}>{JSON.stringify(history, null, 2)}</pre>}</>}
      {error && <p className="form-error" role="alert" style={{color: 'var(--error)', marginTop: '1rem'}}>{error}</p>}
      <div className="modal-actions" style={{display: 'flex', justifyContent: 'flex-end', gap: '12px', marginTop: '2rem', borderTop: '1px solid var(--border)', paddingTop: '1rem'}}><Button type="button" variant="outline" onClick={close}>Cancel</Button><Button disabled={busy || issues.length > 0 || invalid} type="submit">{busy ? 'Validating…' : 'Save content type'}</Button></div>
    </form>
    <aside className="schema-preview" aria-label="Content type previews" style={{borderLeft: '1px solid var(--border)', paddingLeft: '2rem', minWidth: '400px'}}>
      <div className="preview-head" style={{marginBottom: '1rem', borderBottom: '1px solid var(--border)', paddingBottom: '0.5rem'}}>
        <div className="preview-tabs" style={{display: 'flex', gap: '1rem'}}>
          <button className="tab-btn" style={{fontWeight: tab === 'form' ? 'bold' : 'normal', borderBottom: tab === 'form' ? '2px solid var(--accent)' : 'none'}} onClick={() => setTab('form')}>Authoring Form</button>
          <button className="tab-btn" style={{fontWeight: tab === 'schema' ? 'bold' : 'normal', borderBottom: tab === 'schema' ? '2px solid var(--accent)' : 'none'}} onClick={() => setTab('schema')}>Delivery GraphQL</button>
        </div>
      </div>
      <p>{hiddenFieldCount(fields)} private fields are hidden from delivery, including nested fields. Preview values are never saved as content.</p>
      <div className="preview-body">
        {tab === 'form' ? (
          <div className="preview-form">
            {fields.length === 0 && <p className="empty-state">Add a field to preview the entry form.</p>}
            {fields.map((field, i) => (
              <FieldInput 
                key={`${field.name || 'field'}-${i}`} 
                field={field} 
                value={previewData[field.name ?? '']} 
                onChange={value => setPreviewData(previous => ({...previous,[field.name]:value}))} 
                references={references} 
                assets={assets} 
              />
            ))}
          </div>
        ) : (
          <pre className="schema-json" style={{backgroundColor: 'var(--card)', padding: '1rem', borderRadius: '8px', overflowX: 'auto', fontSize: '0.8rem'}}>{deliveryShape(definition?.name || 'Type', key || 'type', fields)}</pre>
        )}
      </div>
    </aside>
  </div></Dialog>
}

export function Types({ types, role, onChanged }: { types: ContentType[]; role: string; onChanged: () => void }) {
  const [editor, setEditor] = useState<ContentType | null | undefined>()
  const [remove, setRemove] = useState<ContentType | null>(null)
  const [error, setError] = useState('')
  async function deleteType() {
    try { await gql('mutation($key:String!){deleteContentType(key:$key)}', { key: remove!.key }); setRemove(null); setError(''); onChanged() }
    catch (reason) { setError(message(reason)) }
  }
  return <><div className="page-heading"><div><div className="eyebrow">YOUR DATA MODEL</div><h1>Content types</h1><p className="subtitle">Define fields once. Query them from every frontend.</p></div>{role === 'admin' && <Button onClick={() => setEditor(null)}><Plus size={16} />New type</Button>}</div>{error && <p className="form-error" role="alert">{error}</p>}<div className="type-grid">{types.map(t => <article className="plain-card" key={t.key}><Blocks size={20} /><h2>{t.name}</h2><code>{t.key}</code><p>{t.fields.length} fields · version {t.version}</p><div className="field-chips">{t.fields.map(f => <span key={f.name}>{f.name} · {f.type}{f.private ? ' · private' : ''}</span>)}</div><p><code>allCms{t.key[0].toUpperCase()}${t.key.slice(1)}</code></p>{role === 'admin' ? <div className="inline-form"><Button variant="outline" onClick={() => setEditor(t)}>Edit schema</Button><button className="text-button muted" onClick={() => setRemove(t)}>Delete empty type</button></div> : <details><summary>View schema</summary><pre>{JSON.stringify(t.fields, null, 2)}</pre></details>}</article>)}</div>{!types.length && <p className="empty-state">Create your first content type to start writing content.</p>}{editor !== undefined && <TypeEditor definition={editor} types={types} onClose={() => setEditor(undefined)} onSaved={() => { setEditor(undefined); onChanged() }} />} {remove && <Dialog title="Delete empty content type?" open onClose={() => setRemove(null)}><p>{remove.name} can be deleted only if it has no entries or entry history.</p>{error && <p className="form-error">{error}</p>}<div className="modal-actions"><Button variant="outline" onClick={() => setRemove(null)}>Cancel</Button><Button onClick={deleteType}>Delete</Button></div></Dialog>}</>
}
