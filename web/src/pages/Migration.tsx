import { useEffect, useRef, useState } from 'react'
import { ArrowDown, ArrowUp, Download, Plus, Trash2, Upload } from 'lucide-react'
import { Button } from '../components/ui/button'
import { Dialog } from '../components/ui/dialog'
import { FieldBuilder } from '../components/FieldBuilder'
import { getContext, message, rest, type Field, type Project } from '../lib/api'
import { toSchema } from '../lib/fields'
import { buildPipeline, exportArchive, type MigrationReport, type TransformStep } from '../lib/migration'
import { useUnsavedChanges } from '../lib/unsaved'

export function Migration({ project, onChanged }: { project: Project; onChanged: () => void }) {
  const [file, setFile] = useState<File | null>(null)
  const [steps, setSteps] = useState<(TransformStep & { id: string })[]>([])
  const [schemas, setSchemas] = useState('{}')
  const [history, setHistory] = useState(false)
  const [privateFields, setPrivateFields] = useState(false)
  const [report, setReport] = useState<MigrationReport | null>(null)
  const [sourceSchemas, setSourceSchemas] = useState<MigrationReport['sourceSchemas']>([])
  const [schemaForms, setSchemaForms] = useState<Record<string, Field[]>>({})
  const [busy, setBusy] = useState<'export' | 'validate' | 'import' | ''>('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [confirm, setConfirm] = useState(false)
  const [limits, setLimits] = useState<{ archiveBytes: number; pipelineBytes: number } | null>(null)
  const errorRef = useRef<HTMLDivElement>(null)
  const reportRef = useRef<HTMLHeadingElement>(null)
  const request = useRef(0)
  useUnsavedChanges(Boolean(busy) || ((steps.length > 0 || schemas !== '{}') && !report?.applied))
  useEffect(() => {
    let active = true
    if (project.role === 'admin') rest<{ archiveBytes: number; pipelineBytes: number }>('/api/migration/limits').then(result => { if (active) setLimits(result) }).catch(reason => { if (active) setError(message(reason)) })
    return () => { active = false; request.current++ }
  }, [project.id, project.role])
  useEffect(() => { if (error) errorRef.current?.focus() }, [error])
  useEffect(() => { if (report) reportRef.current?.focus() }, [report])
  if (project.role !== 'admin') return <section className="plain-card"><h1>Workspace migration</h1><p>Only workspace administrators can import or export content.</p></section>

  function invalidate() { request.current++; setReport(null); setNotice(''); setError(''); setConfirm(false) }
  function edit(index: number, update: Partial<TransformStep>) { invalidate(); setSteps(current => current.map((step, i) => i === index ? { ...step, ...update } : step)) }
  function move(index: number, direction: number) {
    invalidate(); setSteps(current => { const next = [...current]; [next[index], next[index + direction]] = [next[index + direction], next[index]]; return next })
  }
  function useSourceSchemas() {
    invalidate()
    const fields = Object.fromEntries(sourceSchemas.map(type => [type.key, type.fields]))
    setSchemaForms(fields)
    setSchemas(JSON.stringify(Object.fromEntries(sourceSchemas.map(type => [type.key, { fields: type.fields }])), null, 2))
  }
  function editSchema(key: string, fields: Field[]) {
    invalidate()
    setSchemaForms(current => ({ ...current, [key]: fields }))
    const overrides = buildPipeline([], schemas).schemas as Record<string, { fields: Field[] }>
    setSchemas(JSON.stringify({ ...overrides, [key]: { ...overrides[key], fields: toSchema(fields) } }, null, 2))
  }
  async function download() {
    const sequence = ++request.current
    setBusy('export'); setError(''); setNotice('')
    try { await exportArchive(history, privateFields); if (request.current === sequence) setNotice('Your workspace archive is ready to download.') }
    catch (reason) { if (request.current === sequence) setError(message(reason)) }
    finally { if (request.current === sequence) setBusy('') }
  }
  async function validate(apply = false) {
    if (!file || !limits) return
    const sequence = ++request.current
    setConfirm(false); setError(''); setNotice(''); setBusy(apply ? 'import' : 'validate')
    try {
      const pipeline = JSON.stringify(buildPipeline(steps, schemas))
      if (file.size > limits.archiveBytes) throw new Error(`Choose an archive up to ${limits.archiveBytes / 1024 / 1024} MiB.`)
      if (new TextEncoder().encode(pipeline).length > limits.pipelineBytes) throw new Error('Transform pipeline is too large.')
      const body = new FormData()
      body.set('file', file); body.set('pipeline', pipeline); body.set('apply', String(apply))
      if (apply && report) body.set('validation', report.validation)
      const result = await rest<MigrationReport>('/api/migration/import', 'POST', body, getContext(), 300_000)
      if (request.current !== sequence) return
      setReport(result)
      setSourceSchemas(result.sourceSchemas)
      if (result.applied) { setNotice(result.alreadyImported ? 'This archive and pipeline were already imported. No duplicate content was created.' : `Imported into ${project.name}. Working content is saved as drafts.`); onChanged() }
    } catch (reason) {
      if (request.current === sequence) { if (!apply) setReport(null); setError(message(reason)) }
    } finally { if (request.current === sequence) setBusy('') }
  }
  return <div className="migration-page">
    <div className="page-heading"><div><div className="eyebrow">MOVE YOUR CONTENT</div><h1>Import & export</h1><p className="subtitle">Transfer schemas, content, media, and history for {project.name}.</p></div></div>
    {error && <div ref={errorRef} tabIndex={-1} className="notice error-state" role="alert"><strong>Migration needs attention</strong><p>{error}</p><p>Your archive and transform settings are retained. Validate again to check the destination if an import connection was interrupted.</p></div>}
    {notice && <p className="notice" role="status">{notice}</p>}
    {busy && <p className="notice" role="status">{busy === 'export' ? 'Preparing your archive and media…' : busy === 'validate' ? 'Checking the archive, references, media, and transforms…' : 'Importing content and media…'} Keep this page open.</p>}
    <section className="plain-card" aria-labelledby="export-heading"><h2 id="export-heading"><Download size={20} aria-hidden="true" /> Export workspace</h2><p>Download a ZIP containing schemas, independent content snapshots, and original media files. Credentials and accounts are excluded.</p>
      <fieldset className="migration-options" disabled={Boolean(busy)}><legend className="sr-only">Export options</legend>
        <label className="checkbox-label"><input type="checkbox" checked={history} onChange={event => setHistory(event.target.checked)} />Include entry revision history</label>
        <label className="checkbox-label"><input type="checkbox" checked={privateFields} onChange={event => setPrivateFields(event.target.checked)} />Include private fields</label>
      </fieldset>
      {privateFields && <p className="notice">This archive will contain private content. Store and share it securely.</p>}
      <Button onClick={() => void download()} disabled={Boolean(busy)}><Download size={16} aria-hidden="true" />{busy === 'export' ? 'Preparing archive…' : 'Download workspace ZIP'}</Button>
    </section>
    <section className="plain-card editor-form" aria-labelledby="import-heading"><h2 id="import-heading"><Upload size={20} aria-hidden="true" /> Import into {project.name}</h2><p>The destination must have no content types, entries, or assets. New working content becomes drafts. Source publication states and history are retained; source schedules will not run.</p>
      <fieldset className="migration-controls" disabled={Boolean(busy)}><legend className="sr-only">Archive and transform pipeline</legend>
        <label htmlFor="migration-file">Workspace ZIP archive<input id="migration-file" type="file" accept=".zip,application/zip" aria-describedby="archive-help" onChange={event => { invalidate(); setSourceSchemas([]); setSchemaForms({}); setFile(event.target.files?.[0] || null) }} /></label>
        <small id="archive-help">{limits ? `Up to ${limits.archiveBytes / 1024 / 1024} MiB in the browser. Larger archives can use the operator CLI.` : 'Loading archive limits…'}</small>
        <div className="migration-section-heading"><div><h3>Transform pipeline</h3><p>Steps run from top to bottom on draft, published, and scheduled values. Original source values stay in history.</p></div><Button variant="outline" type="button" onClick={() => { invalidate(); setSteps(current => [...current, { id: crypto.randomUUID(), op: 'rename', path: '', typeKey: '', argument: '' }]) }} disabled={steps.length >= 100}><Plus size={16} aria-hidden="true" />Add step</Button></div>
        {!steps.length && <p className="migration-empty">No transforms. Content will use its source schema.</p>}
        <ol className="migration-steps">{steps.map((step, index) => <li key={step.id}><fieldset className="field-group"><legend>Step {index + 1}</legend><div className="migration-step-fields">
          <label>Operation<select aria-label={`Step ${index + 1} operation`} value={step.op} onChange={event => edit(index, { op: event.target.value as TransformStep['op'], argument: event.target.value === 'convert' ? 'text' : '' })}><option value="rename">Rename field</option><option value="default">Default value</option><option value="drop">Drop field</option><option value="convert">Convert value</option></select></label>
          <label>Content type<input aria-label={`Step ${index + 1} content type`} value={step.typeKey} placeholder="All types" list="migration-type-keys" onChange={event => edit(index, { typeKey: event.target.value })} /></label>
          <label>Field path<input aria-label={`Step ${index + 1} field path`} value={step.path} placeholder="sections.*.heading" onChange={event => edit(index, { path: event.target.value })} /></label>
          {step.op === 'convert' ? <label>Convert to<select aria-label={`Step ${index + 1} destination type`} value={step.argument} onChange={event => edit(index, { argument: event.target.value })}><option value="text">Text</option><option value="number">Number</option><option value="boolean">Boolean</option></select></label> : step.op !== 'drop' && <label>{step.op === 'rename' ? 'New field name' : 'Default value (JSON)'}<input aria-label={`Step ${index + 1} ${step.op === 'rename' ? 'new field name' : 'default value'}`} value={step.argument} placeholder={step.op === 'rename' ? 'title' : '"Untitled"'} onChange={event => edit(index, { argument: event.target.value })} /></label>}
        </div><div className="row-actions"><Button variant="outline" type="button" aria-label={`Move step ${index + 1} up`} disabled={index === 0} onClick={() => move(index, -1)}><ArrowUp size={16} aria-hidden="true" />Up</Button><Button variant="outline" type="button" aria-label={`Move step ${index + 1} down`} disabled={index === steps.length - 1} onClick={() => move(index, 1)}><ArrowDown size={16} aria-hidden="true" />Down</Button><Button variant="ghost" type="button" aria-label={`Remove step ${index + 1}`} onClick={() => { invalidate(); setSteps(current => current.filter((_, i) => i !== index)) }}><Trash2 size={16} aria-hidden="true" />Remove</Button></div></fieldset></li>)}</ol>
        <datalist id="migration-type-keys">{sourceSchemas.map(type => <option key={type.key} value={type.key} />)}</datalist>
        {!!sourceSchemas.length && <details><summary>Source schemas ({sourceSchemas.length})</summary><pre tabIndex={0}>{JSON.stringify(sourceSchemas.map(({ key, name, fields }) => ({ key, name, fields })), null, 2)}</pre><Button type="button" variant="outline" onClick={useSourceSchemas}>Customize destination schemas</Button></details>}
        {Object.entries(schemaForms).map(([key, fields]) => <section className="field-group" key={key} aria-label={`Destination schema ${key}`}><h3>Destination fields: {key}</h3><p>Match these field names and types to the output of your transform steps.</p><FieldBuilder value={fields} selfKey={key} types={sourceSchemas.map(type => ({ ...type, id: type.key }))} onChange={next => editSchema(key, next)} /></section>)}
        <details><summary>Destination schemas (advanced)</summary><p>If transforms change field names or types, supply the complete destination fields for those content types. Unlisted types keep their source schema. Validate once to inspect the source schemas and open the field editor.</p><label>Schema overrides (JSON)<textarea className="code-input" rows={10} value={schemas} onChange={event => { invalidate(); setSchemaForms({}); setSchemas(event.target.value) }} spellCheck={false} aria-describedby="schema-help" /></label><small id="schema-help">Example: {`{"article":{"fields":[{"name":"title","type":"text"}]}}`}</small></details>
      </fieldset>
      <div className="row-actions"><Button onClick={() => void validate()} disabled={Boolean(busy) || !file || !limits}>{busy === 'validate' ? 'Validating…' : 'Validate import'}</Button><a className="text-button" href="#settings">Create an empty workspace in Settings</a></div>
    </section>
    {report && <section className="plain-card migration-review" aria-labelledby="migration-review"><h2 id="migration-review" tabIndex={-1} ref={reportRef}>{report.applied ? 'Import complete' : 'Validation passed — review import'}</h2><p>Destination: <strong>{project.name}</strong>. {report.applied ? 'Source publication states remain in revision history.' : 'No content or media has been committed. Import will validate this archive and pipeline again.'}</p>
      <dl className="migration-counts">{(['schemas', 'entries', 'assets', 'revisions'] as const).map((key, index) => <div key={key}><dt>{['Content types', 'Entries', 'Assets', 'History records'][index]}</dt><dd>{report.counts[key].toLocaleString()}</dd></div>)}</dl>
      <p>Working entries become drafts. Source trash stays trashed. Published and scheduled source snapshots are preserved in history, with no live publication or active schedules.</p>
      {report.includePrivate && <p className="notice">This archive includes private fields.</p>}
      <details><summary>Omitted private fields ({report.omittedFields.length})</summary>{report.omittedFields.length ? <ul>{report.omittedFields.map(path => <li key={path}><code>{path}</code></li>)}</ul> : <p>No private field omissions were reported.</p>}</details>
      <details><summary>Applied transforms ({report.transformations.length})</summary>{report.transformations.length ? <><div className="table-scroll"><table><caption className="sr-only">First 100 applied transforms</caption><thead><tr><th>Entry</th><th>Snapshot</th><th>Step</th><th>Operation</th><th>Field</th></tr></thead><tbody>{report.transformations.slice(0, 100).map((change, index) => <tr key={index}><td>{change.entryId}</td><td>{change.snapshot}</td><td>{change.step + 1}</td><td>{change.op}</td><td>{change.path}</td></tr>)}</tbody></table></div>{report.transformations.length > 100 && <p>Showing the first 100 transformations.</p>}</> : <p>No field transformations were needed.</p>}</details>
      {!report.applied && <Button onClick={() => setConfirm(true)} disabled={Boolean(busy)}>Import reviewed archive</Button>}
      {report.applied && <a className="button button-outline" href="#content">Open imported content</a>}
    </section>}
    <Dialog title={`Import into ${project.name}?`} open={confirm} onClose={() => setConfirm(false)}><div className="editor-form"><p>Import {report?.counts.entries.toLocaleString()} {report?.counts.entries === 1 ? 'entry' : 'entries'} and {report?.counts.assets.toLocaleString()} assets into this workspace. Working entries will be drafts, and source schedules will remain inactive.</p><p>Existing content will not be overwritten. The archive and pipeline will be checked again before committing.</p><div className="row-actions"><Button variant="outline" onClick={() => setConfirm(false)}>Cancel</Button><Button onClick={() => void validate(true)}>Confirm import</Button></div></div></Dialog>
  </div>
}
