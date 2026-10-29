import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ArrowLeft, CalendarClock, Check, Circle, Copy, Eye, History, FileText, Link as LinkIcon } from 'lucide-react'
import { useDraftAutosave } from '../lib/autosave'
import { useUnsavedChanges } from '../lib/unsaved'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { SeoEntryPanel } from '../components/SeoEntryPanel'
import { focusSeoField } from '../lib/seo'
import { readContentRoute } from '../lib/navigation'
import { FieldInput, fieldInputId } from '../components/Fields'
import { RevisionCompare, type Revision } from '../components/RevisionCompare'
import { isEntryValid, validateEntry } from '../lib/validation'
import { initialData } from '../lib/fields'
import { creationLabels, timestamp, typeOrder, type DuplicationSource, type EntryPage as Page } from '../lib/entries'
import { ApiError, getContext, draftReceiptQuery, entryFields, gql, message, saveEntryMutation, type Asset, type ContentType, type Entry } from '../lib/api'
import { canonicalSlug, encodeWebsitePath, slugify } from '../lib/slugify'

function localDateTime(value: Date) {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}T${String(value.getHours()).padStart(2, '0')}:${String(value.getMinutes()).padStart(2, '0')}`
}
function suggestedSlug(value: string) {
  try {
    return slugify(value)
  } catch {
    return canonicalSlug(value)
  }
}
function publicPath(definition: ContentType, slug: string, data: Record<string, unknown>) {
  const key = definition.key
  const kind = definition.fields.find(field => field.name === 'kind')
  if (key === 'sitePage' && (slug === 'home' || kind && !kind.private && data.kind === 'home')) return '/'
  const prefix = key === 'sitePost' ? '/blog/' : key === 'siteProject' ? '/projects/' : '/'
  return encodeWebsitePath(`${prefix}${slug}`)
}
function dataForType(definition: ContentType, defaultLocale = 'en') {
  const data = initialData(definition.fields, defaultLocale)
  if (['siteProject', 'sitePost'].includes(definition.key)) {
    data.order = 10; data.kind = 'page'
    data.parentSlug = definition.key === 'siteProject' ? 'projects' : 'blog'
  }
  return data
}

export function EntryEditor({
  entry: initialEntry,
  types,
  initialType,
  seed,
  editable,
  role = editable ? 'editor' : 'reader',
  onClose,
  onSaved,
  onCopyLink,
  onDuplicate,
  backLabel = 'Back to content',
  projectId,
  defaultLocale = 'en',
  locales = ['en'],
  previewOrigin,
}: {
  entry: Entry | null
  types: ContentType[]
  initialType: string
  seed?: DuplicationSource | null
  editable: boolean
  role?: string
  onClose: () => void
  onSaved: (text: string, draft?: Entry) => void
  onCopyLink?: (entry: Entry) => void
  onDuplicate?: (entry: Entry) => void
  previewOrigin?: string | null
  backLabel?: string
  projectId?: string
  defaultLocale?: string
  locales?: string[]
}) {
  const context = useRef(getContext()).current
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => { heading.current?.focus(); window.scrollTo(0, 0) }, [initialEntry?.id])
  const [key, setKey] = useState(initialEntry?.typeKey || seed?.typeKey || initialType || types[0]?.key || '')
  const definition = types.find(t => t.key === key)!
  const [data, setData] = useState<Record<string, unknown>>(() => {
    if (initialEntry?.data) return initialEntry.data
    if (seed?.data) return JSON.parse(JSON.stringify(seed.data))
    return dataForType(definition, defaultLocale)
  })
  const [slug, setSlug] = useState(initialEntry?.slug || seed?.slug || '')
  const [slugEdited, setSlugEdited] = useState(Boolean(initialEntry || seed))
  const [status, setStatus] = useState('draft')
  const [schedule, setSchedule] = useState(initialEntry?.scheduledAt ? localDateTime(new Date(initialEntry.scheduledAt)) : localDateTime(new Date(Date.now() + 3600000)))
  const [error, setError] = useState('')
  const [pendingPublication,setPendingPublication]=useState<Record<string,unknown>|null>(null)
  const [publicationState,setPublicationState]=useState('')
  const [busy, setBusy] = useState(false)
  const [references, setReferences] = useState<Entry[]>([])
  const [assets, setAssets] = useState<Asset[]>([])
  const [preview, setPreview] = useState<{id:string;previewUrl:string;revision:number;expiresAt:string} | null>(null)
  const [history, setHistory] = useState<Revision[] | null>(null)
  const [showCompare, setShowCompare] = useState(false)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const clearError = (p?: string, descendants = false) => {
    if (!p) { setFieldErrors({}); return }
    setFieldErrors(prev => Object.fromEntries(Object.entries(prev).filter(([path]) => path !== p && !(descendants && (path.startsWith(`${p}.`) || path.startsWith(`${p}[`))))))
  }
  const isUnsavedDuplicate = Boolean(seed && !initialEntry)
  const autosave = useDraftAutosave(
    initialEntry,
    { typeKey: key, slug, data },
    editable && !busy && !pendingPublication && !showCompare && initialEntry?.status !== 'deleted' && !isUnsavedDuplicate,
    isEntryValid(definition.fields, data, slug),
    900,
    !initialEntry
  )
  useEffect(() => { if (Object.keys(autosave.validationErrors).length) setFieldErrors(autosave.validationErrors) }, [autosave.validationErrors])
  useEffect(() => { setFieldErrors({}) }, [definition.version, projectId])
  const seoRoute = readContentRoute()
  useEffect(() => {
    if (!initialEntry || seoRoute.entry !== initialEntry.id || !seoRoute.field) return
    const frame = requestAnimationFrame(() => focusSeoField(seoRoute.field))
    return () => cancelAnimationFrame(frame)
  }, [initialEntry?.id, seoRoute.entry, seoRoute.field])
  const entry = autosave.entry
  const confirmClose = useUnsavedChanges(editable && (isUnsavedDuplicate || busy || Boolean(pendingPublication) || autosave.dirty || status !== 'draft'))
  const close = () => { if (!busy && confirmClose()) onClose() }
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone
  const livePath = entry ? publicPath(definition, entry.publishedSnapshot?.slug || entry.publishedSlug || entry.slug, entry.publishedSnapshot?.data || entry.publishedData || entry.data) : ''
  const nextPath = publicPath(definition, slug, data)
  const fields = definition.fields.filter(field => !(['siteProject', 'sitePost'].includes(key) && ['kind', 'parentSlug'].includes(field.name)))
  useEffect(() => { let alive = true; gql<{ entries: Page; assets: Asset[] }>(`{entries(first:100){nodes{${entryFields}} total endCursor hasNextPage} assets(first:100){id name mime size url}}`, undefined, context).then(result => { if (alive) { setReferences(result.entries.nodes); setAssets(result.assets) } }).catch(reason => { if (alive) setError(message(reason)) }); return () => { alive = false } }, [context])
  async function save(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('')
    const clientErrors = validateEntry(definition.fields, data, slug)
    if (Object.keys(clientErrors).length > 0) {
      setFieldErrors(clientErrors)
      setBusy(false)
      const first = Object.keys(clientErrors)[0]
      const el = document.getElementById(fieldInputId(first))
      if (el) el.focus()
      return
    }
    try {
      if(pendingPublication){await checkPublication(pendingPublication,false);return}
      let scheduledAt = null
      if (status === 'scheduled') {
        const date = new Date(schedule)
        if (!Number.isFinite(date.getTime()) || date.getTime() <= Date.now()) throw new Error('Choose a future date and time to schedule this entry.')
        scheduledAt = date.toISOString()
      }
      const saved = await autosave.flush()
      if (status === 'draft') {
        onSaved(seed && !initialEntry ? 'Duplicated draft saved. Original entry is unchanged.' : 'Draft saved. Existing live content and schedule are preserved.', saved || undefined)
        return
      }
      const operation={typeKey:key,slug,data,status,id:saved?.id,version:saved?.version,scheduledAt,requestKey:crypto.randomUUID()}
      setPendingPublication(operation)
      await checkPublication(operation,true)
    } catch (reason) {
      if (reason instanceof ApiError && reason.fieldErrors) {
        setFieldErrors(reason.fieldErrors)
        if (reason.requestId) setError(message(reason))
        const first = Object.keys(reason.fieldErrors)[0]
        setTimeout(() => {
          const el = document.getElementById(fieldInputId(first))
          if (el) el.focus()
        }, 0)
      } else if (reason instanceof ApiError && reason.fieldPath) {
        setFieldErrors({ [reason.fieldPath]: reason.message })
        setTimeout(() => {
          const el = document.getElementById(fieldInputId(reason.fieldPath!))
          if (el) el.focus()
        }, 0)
      } else {
        setError(message(reason))
      }
    }
    finally { setBusy(false) }
  }
  async function checkPublication(operation:Record<string,unknown>,send:boolean) {
    const complete=()=>{setPendingPublication(null);onSaved(operation.status==='published'?'Published in CMS. Website refresh requested; display is not yet confirmed.':`Captured schedule saved for ${timestamp(String(operation.scheduledAt))} (${timezone}).`)}
    try {
      if(send){await gql(saveEntryMutation,operation,context);complete();return}
      const result=await gql<{draftReceipt:Entry|null}>(draftReceiptQuery,{key:operation.requestKey},context)
      if(result.draftReceipt){complete();return}
      setPublicationState('Publication outcome is unconfirmed. Check again or explicitly retry the same operation. Your values are retained.')
    }catch(reason){
      if(reason instanceof ApiError && reason.uncertain){setPublicationState('Response lost. Checking the saved operation…');if(send)await checkPublication(operation,false);else setPublicationState('Outcome is unconfirmed. Check again when connected.')}
      else {if(send)setPendingPublication(null);throw reason}
    }
  }
  async function preparePreview() {
    setBusy(true); setError(''); setPreview(null)
    try {
      const saved = await autosave.flush()
      if (!saved) throw new Error('Complete and save this draft before previewing.')
      const result = await gql<{createPreviewGrant:{id:string;previewUrl:string;revision:number;expiresAt:string}}>('mutation($id:ID!,$version:Int!){createPreviewGrant(id:$id,version:$version)}', {id:saved.id,version:saved.version},context)
      if (!result.createPreviewGrant.previewUrl) throw new Error('Ask an administrator to set the website preview origin in Settings.')
      setPreview(result.createPreviewGrant)
    } catch(reason) { setError(message(reason)) }
    finally { setBusy(false) }
  }
  async function loadHistory() {
    try { const result = await gql<{ revisions: Revision[] }>('query($id:ID!){revisions(id:$id){number snapshot author createdAt}}', { id: entry!.id }, context); setHistory(result.revisions) }
    catch (reason) { setError(message(reason)) }
  }
  async function restore(number: number) {
    setBusy(true)
    try { const saved = initialEntry?.status === 'deleted' ? initialEntry : await autosave.flush(); await gql('mutation($id:ID!,$number:Int!,$version:Int!){restoreEntry(id:$id,number:$number,version:$version){id}}', { id: saved!.id, number, version: saved!.version }, context); onSaved('Revision restored as a draft.') }
    catch (reason) { setError(message(reason)); throw reason }
    finally { setBusy(false) }
  }
  async function publicationAction(action: 'unpublishEntry' | 'cancelSchedule') {
    if (!entry) return
    setBusy(true); setError('')
    try {
      const saved = await autosave.flush()
      await gql(`mutation($id:ID!,$version:Int!){${action}(id:$id,version:$version){id}}`, { id: saved!.id, version: saved!.version }, context)
      onSaved(action === 'unpublishEntry' ? 'Entry unpublished. Draft and history retained.' : 'Schedule cancelled. Live content preserved.')
    } catch (reason) { setError(message(reason)) }
    finally { setBusy(false) }
  }
  return <section className="entry-page" aria-label="Entry editor">
    <button className="entry-back text-button" type="button" disabled={busy} onClick={close}><ArrowLeft size={16} aria-hidden="true" />{backLabel}</button>
    <header className="entry-page-heading">
      <div className="eyebrow">{editable ? 'CONTENT EDITOR' : 'CONTENT DETAILS'}</div>
      <h1 ref={heading} tabIndex={-1}>{entry?.title || (seed && !initialEntry ? `${seed.title} (Copy)` : creationLabels[key] || 'New entry')}</h1>
      <div className="editor-meta"><span className={`content-type-label ${key}`}><FileText size={14} aria-hidden="true" />{definition.name}</span>{entry && <><Badge className={entry.isLive ? 'published' : entry.status}>{entry.status === 'deleted' ? 'Trash' : entry.isLive ? 'Live' : 'Unpublished'}</Badge>{entry.hasUnpublishedChanges && entry.status !== 'deleted' && <Badge>Unpublished changes</Badge>}<small>Version {entry.version}</small>{onCopyLink && <Button type="button" variant="ghost" onClick={() => onCopyLink(entry)} title="Copy link to this entry"><LinkIcon size={14} aria-hidden="true" />Copy link</Button>}{onDuplicate && editable && entry.status !== 'deleted' && <Button type="button" variant="ghost" onClick={() => onDuplicate(entry)} title="Duplicate into a new draft"><Copy size={14} aria-hidden="true" />Duplicate</Button>}</>}</div>
    </header>
    {seoRoute.seoSnapshot === 'live' && <p className="notice" role="status">You opened a live SEO finding. You are viewing the editable draft; save and publish fixes to update live content.</p>}
    <form className="editor-form entry-page-form" noValidate onSubmit={save}>
      {autosave.error && <div className="form-error" role="alert">{autosave.error}<Button type="button" variant="outline" onClick={autosave.state === 'Conflict' ? autosave.compare : autosave.retry}>{autosave.state === 'Conflict' ? 'Compare server version' : 'Check and retry'}</Button></div>}
      {autosave.server && <section><h3>Server version {autosave.server.version}</h3><details><summary>Server data</summary><pre tabIndex={0}>{JSON.stringify(autosave.server.data,null,2)}</pre></details><p>Your edits remain in the form above. Copy any changes you want to keep before reloading.</p><Button type="button" onClick={() => { if (confirmClose()) {const next=autosave.reload();if(next){setData(next.data);setSlug(next.slug);setKey(next.typeKey);setStatus('draft')}} }}>Discard local edits and reload server</Button></section>}
      <div className="entry-workspace">
      {seed && !entry && (
        <div className="duplication-banner" role="status">
          <Copy size={16} aria-hidden="true" />
          <span>
            Duplicating from <strong>{seed.title}</strong> (Version {seed.version}). Unsaved local source changes are not included; the original remains unchanged. This draft is not saved until you click Save draft.
          </span>
        </div>
      )}
      <fieldset className="entry-writing editor-surface" disabled={!editable || busy || Boolean(pendingPublication) || initialEntry?.status === 'deleted'}><div className="editor-section-heading"><h2>Content</h2><p>Write and shape the content for this entry.</p></div>
        {!entry && <label>Content type<select value={key} onChange={event => { setKey(event.target.value); setFieldErrors({}); setData(dataForType(types.find(t => t.key === event.target.value)!, defaultLocale)) }}>{types.map(t => <option key={t.key} value={t.key}>{t.name}</option>)}</select></label>}
        {Object.keys(fieldErrors).length > 0 && (
          <div className="error-summary" role="alert" aria-labelledby="error-summary-heading">
            <strong id="error-summary-heading">Please fix the following errors:</strong>
            <ul>
              {Object.entries(fieldErrors).map(([errPath, errText]) => {
                const inputId = fieldInputId(errPath)
                return (
                  <li key={errPath}>
                    <a
                      href={`#${inputId}`}
                      onClick={e => {
                        e.preventDefault()
                        const el = document.getElementById(inputId)
                        if (el) {
                          el.focus()
                          if (typeof el.scrollIntoView === 'function') {
                            el.scrollIntoView({ behavior: 'smooth', block: 'center' })
                          }
                        }
                      }}
                    >
                      {errText}
                    </a>
                  </li>
                )
              })}
            </ul>
          </div>
        )}
        {fields.map(field => (
          <FieldInput
            key={field.name}
            field={field}
            value={data[field.name]}
            onChange={value => {
              clearError(`data.${field.name}`)
              setData(old => ({ ...old, [field.name]: value }))
              if (field.name === 'title' && !slugEdited) {
                const title = typeof value === 'string' ? value : value && typeof value === 'object' ? Object.values(value)[0] : ''
                setSlug(suggestedSlug(String(title || '')))
              }
            }}
            projectId={projectId}
            defaultLocale={defaultLocale}
            locales={locales}
            editable={editable && !busy && !pendingPublication && initialEntry?.status !== 'deleted'}
            references={references}
            assets={assets}
            errors={fieldErrors}
            onClearError={clearError}
          />
        ))}
        <section className="entry-details"><h2>Entry details</h2>
        <p className="field-help">New slugs follow the title until you edit the slug. Existing slugs stay stable; draft slug changes reach the website only when published.</p>
        <label htmlFor="field-slug">Slug{fieldErrors['slug'] && <span id="error-slug" className="field-error" role="alert">{fieldErrors['slug']}</span>}</label>
        <input
          id="field-slug"
          required
          maxLength={220}
          value={slug}
          aria-invalid={Boolean(fieldErrors['slug'])}
          aria-describedby={fieldErrors['slug'] ? 'error-slug' : undefined}
          onChange={event => {
            setSlugEdited(true)
            clearError('slug')
            setSlug(suggestedSlug(event.target.value))
          }}
        />
        </section>
      </fieldset>
      <aside className="entry-sidebar" aria-label="Entry controls">
      <fieldset className="publishing-fieldset" disabled={!editable || busy || Boolean(pendingPublication) || initialEntry?.status === 'deleted'}>
        <section className="publishing-panel" aria-label="Publishing options">
          <div className="publishing-title"><CalendarClock size={16} /><h2>Publishing</h2></div><p className="publishing-intro">{entry?.isLive ? 'You’re editing a draft. Your live content stays available until you publish.' : 'Choose when this entry becomes available to your frontends.'}</p>
          {status === 'published' && entry?.isLive && nextPath !== livePath && ['sitePost', 'siteProject', 'sitePage'].includes(key) && <p className="notice" role="status">Publishing changes the public URL from <code>{livePath}</code> to <code>{nextPath}</code>. The previous URL will redirect to the new URL while this entry is live. Draft saves keep the current public URL.</p>}
          <p className="field-help">Select a publishing mode, then use the action below.</p>
          <div className="publishing-options" role="group" aria-label="Publishing mode">{[
            { value: 'draft', label: 'Draft', description: 'Preserve live content and schedule' },
            { value: 'published', label: 'Immediate publication', description: 'Publish when you confirm below' },
            { value: 'scheduled', label: 'Scheduled publication', description: entry?.scheduledAt ? 'Replace the captured schedule' : 'Capture these edits for later' },
          ].filter(option => !isUnsavedDuplicate || option.value === 'draft').map(option => <button type="button" key={option.value} className={status === option.value ? 'selected' : ''} aria-pressed={status === option.value} onClick={() => setStatus(option.value)}><span>{option.label}{status === option.value && <Check size={12} />}</span><small>{option.description}</small></button>)}</div>
          {status === 'scheduled' ? <div className="schedule-fields"><label>Publish on<input type="datetime-local" required min={localDateTime(new Date(Date.now() + 60000))} value={schedule} onChange={event => setSchedule(event.target.value)} /></label><p className="field-help">Timezone: <strong>{timezone}</strong>. This captures the selected draft. Later draft edits will not change it. Existing live content stays available.</p></div> : <p className="field-help">{status === 'published' ? 'Publishing makes this entry available to your connected frontends.' : 'Draft saves preserve existing live content and any pending schedule.'}</p>}
          {entry?.scheduledAt && <p className="field-help">Scheduled revision {entry.scheduledRevision} for {timestamp(entry.scheduledAt)} ({timezone}). {entry.scheduledRevision !== entry.version && 'Newer draft changes are not scheduled. Use Replace schedule to include them.'}</p>}
          {entry?.scheduleError && <p className="form-error" role="alert">Publication failed: {entry.scheduleError.message} Resolve the cause and schedule again.</p>}
          {editable && entry?.scheduledAt && <Button type="button" variant="outline" onClick={() => publicationAction('cancelSchedule')}>Cancel schedule</Button>}
          {editable && entry?.isLive && <Button type="button" variant="outline" onClick={() => publicationAction('unpublishEntry')}>Unpublish</Button>}
        </section>
      </fieldset>
      {editable && initialEntry?.status !== 'deleted' && typeOrder.includes(key) && <section className="editor-surface preview-controls"><h2><Eye size={17} aria-hidden="true" />Website preview</h2><p>Review a saved draft on your website before publishing.</p>{previewOrigin === null ? <p>{role === 'admin' ? <a className="button button-outline" href={`#settings?workspace=${encodeURIComponent(projectId || context.project)}&section=website-preview`}>Connect website preview</a> : 'Ask an administrator to connect the website preview in Settings.'}</p> : <Button type="button" variant="outline" disabled={busy || isUnsavedDuplicate} onClick={preparePreview}>Save draft & prepare website preview</Button>}{preview && <p><a href={preview.previewUrl} target="_blank" rel="noopener noreferrer">Open saved revision {preview.revision}</a> · expires {timestamp(preview.expiresAt)} <Button type="button" variant="outline" onClick={async()=>{try{await gql('mutation($id:ID!){revokePreviewGrant(id:$id)}',{id:preview.id});setPreview(null)}catch(reason){setError(message(reason))}}}>Revoke preview</Button></p>}</section>}
      {pendingPublication && <section role="status"><p>{publicationState || 'Saving publication…'}</p><Button type="button" disabled={busy} onClick={async()=>{setBusy(true);try{await checkPublication(pendingPublication,false)}catch(reason){setError(message(reason))}finally{setBusy(false)}}}>Check outcome</Button><Button type="button" variant="outline" disabled={busy} onClick={async()=>{setBusy(true);try{await checkPublication(pendingPublication,true)}catch(reason){setError(message(reason))}finally{setBusy(false)}}}>Retry same operation</Button></section>}
      <SeoEntryPanel entry={entry} dirty={autosave.dirty} projectId={projectId || context.project} />
      {entry && <section className="editor-surface history-controls"><h2><History size={17} aria-hidden="true" />Revision history</h2><p>Version {entry.version} · updated {timestamp(entry.updatedAt)}</p><div className="inline-form"><Button type="button" variant="outline" disabled={busy} onClick={loadHistory}>{history ? 'Refresh history' : 'History & restore'}</Button><Button type="button" variant="outline" disabled={busy} onClick={async () => { if (!history) await loadHistory(); setShowCompare(true) }}>Compare revisions & live</Button></div></section>}
      </aside>
      </div>
      {history && <section className="revision-list"><h3>History</h3>{history.map(revision => <article key={revision.number}><div className="inline-form"><strong>Version {revision.number}</strong><small>{revision.author} · {new Date(revision.createdAt).toLocaleString()}</small>{editable && <Button type="button" variant="outline" disabled={busy} onClick={() => { if (window.confirm(`Restore revision ${revision.number} as a new draft? Live content and schedules will be preserved.`)) void restore(revision.number).catch(() => {}) }}>Restore draft</Button>}<Button type="button" variant="ghost" disabled={busy} onClick={() => setShowCompare(true)}>Compare</Button></div><details><summary>Preview this revision</summary><pre tabIndex={0}>{JSON.stringify(revision.snapshot, null, 2)}</pre></details></article>)}</section>}
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="entry-actionbar"><div className="entry-save-state" role="status">{editable ? <>{autosave.state === 'Saved' ? <Check size={16} aria-hidden="true" /> : <Circle size={16} aria-hidden="true" />}<span>Draft: {autosave.state}{autosave.state === 'Incomplete' && ' — complete required fields to autosave.'}</span></> : <span>Read-only access</span>}</div>{editable && initialEntry?.status !== 'deleted' && <Button type="submit" disabled={busy}>{busy ? 'Saving…' : pendingPublication ? 'Check outcome' : status === 'published' ? 'Publish now' : status === 'scheduled' ? 'Schedule publication' : 'Save draft'}</Button>}</div>
    </form>
    {showCompare && entry && (
      <RevisionCompare
        entry={entry}
        definition={definition}
        revisions={history || []}
        references={references}
        assets={assets}
        role={role}
        onClose={() => setShowCompare(false)}
        onRestore={async (revNum) => {
          await restore(revNum)
          setShowCompare(false)
        }}
      />
    )}
  </section>
}
