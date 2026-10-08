import { useEffect, useState, type FormEvent } from 'react'
import { CalendarClock, Check, FileText, Folder, Image, NotebookPen, Plus, Search, Settings2 } from 'lucide-react'
import { useDraftAutosave } from '../lib/autosave'
import { useUnsavedChanges } from '../lib/unsaved'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Dialog } from '../components/ui/dialog'
import { FieldInput } from '../components/Fields'
import { entryFields, gql, message, saveEntryMutation, slugify, type Asset, type ContentType, type Entry, type Field } from '../lib/api'

type Page = { nodes: Entry[]; total: number; endCursor: string | null; hasNextPage: boolean }
type Group = { key: string; name: string; count: number }
type Revision = { number: number; snapshot: Record<string, unknown>; author: string; createdAt: string }
const typeIcons = { siteProject: Folder, sitePost: NotebookPen, sitePage: FileText, siteSlide: Image, siteProfile: Settings2 }
const typeOrder = ['siteProject', 'sitePost', 'sitePage', 'siteSlide', 'siteProfile']
const creationLabels: Record<string, string> = { siteProject: 'New project', sitePost: 'New blog post', sitePage: 'New page', siteSlide: 'New slide' }
const timestamp = (value: string) => new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
function localDateTime(value: Date) {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}T${String(value.getHours()).padStart(2, '0')}:${String(value.getMinutes()).padStart(2, '0')}`
}
export function initialData(fields: Field[]): Record<string, unknown> {
  return Object.fromEntries(fields.map(f => [f.name, f.localized ? { en: f.type === 'boolean' ? false : null } : f.type === 'boolean' ? false : f.type === 'list' ? [] : f.type === 'object' ? initialData(f.fields || []) : null]))
}
function dataForType(definition: ContentType) {
  const data = initialData(definition.fields)
  if (['siteProject', 'sitePost'].includes(definition.key)) {
    data.order = 10; data.kind = 'page'
    data.parentSlug = definition.key === 'siteProject' ? 'projects' : 'blog'
  }
  return data
}

function EntryEditor({ entry: initialEntry, types, initialType, editable, onClose, onSaved }: { entry: Entry | null; types: ContentType[]; initialType: string; editable: boolean; onClose: () => void; onSaved: (text: string) => void }) {
  const [key, setKey] = useState(initialEntry?.typeKey || initialType || types[0]?.key || '')
  const definition = types.find(t => t.key === key)!
  const [data, setData] = useState(initialEntry?.data || dataForType(definition))
  const [slug, setSlug] = useState(initialEntry?.slug || '')
  const [slugEdited, setSlugEdited] = useState(Boolean(initialEntry))
  const [status, setStatus] = useState('draft')
  const [schedule, setSchedule] = useState(initialEntry?.scheduledAt ? localDateTime(new Date(initialEntry.scheduledAt)) : localDateTime(new Date(Date.now() + 3600000)))
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [references, setReferences] = useState<Entry[]>([])
  const [assets, setAssets] = useState<Asset[]>([])
  const [history, setHistory] = useState<Revision[] | null>(null)
  const requiredComplete = (fields: Field[], values: Record<string, unknown>): boolean => fields.every(f => !f.required || (values[f.name] !== null && values[f.name] !== undefined && values[f.name] !== ''))
  const autosave = useDraftAutosave(initialEntry, {typeKey:key, slug, data}, editable && !busy && initialEntry?.status !== 'deleted', Boolean(slug) && requiredComplete(definition.fields,data))
  const entry = autosave.entry
  const confirmClose = useUnsavedChanges(editable && (busy || autosave.dirty || status !== 'draft'))
  const close = () => { if (!busy && confirmClose()) onClose() }
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone
  const fields = definition.fields.filter(field => !(['siteProject', 'sitePost'].includes(key) && ['kind', 'parentSlug'].includes(field.name)))
  useEffect(() => { gql<{ entries: Page; assets: Asset[] }>(`{entries(first:100){nodes{${entryFields}} total endCursor hasNextPage} assets(first:100){id name mime size url}}`).then(result => { setReferences(result.entries.nodes); setAssets(result.assets) }).catch(reason => setError(message(reason))) }, [])
  async function save(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('')
    try {
      let scheduledAt = null
      if (status === 'scheduled') {
        const date = new Date(schedule)
        if (!Number.isFinite(date.getTime()) || date.getTime() <= Date.now()) throw new Error('Choose a future date and time to schedule this entry.')
        scheduledAt = date.toISOString()
      }
      const saved = await autosave.flush()
      if (status === 'draft') { onSaved('Draft saved. Existing live content and schedule are preserved.'); return }
      await gql(saveEntryMutation, { typeKey: key, slug, data, status, id: saved?.id, version: saved?.version, scheduledAt })
      onSaved(status === 'published' ? 'Entry published.' : status === 'scheduled' ? `Scheduled for ${timestamp(scheduledAt!)} (${timezone}).` : 'Draft saved. Existing live content and schedule are preserved.')
    } catch (reason) { setError(message(reason)) }
    finally { setBusy(false) }
  }
  async function loadHistory() {
    try { const result = await gql<{ revisions: Revision[] }>('query($id:ID!){revisions(id:$id){number snapshot author createdAt}}', { id: entry!.id }); setHistory(result.revisions) }
    catch (reason) { setError(message(reason)) }
  }
  async function restore(number: number) {
    setBusy(true)
    try { const saved = initialEntry?.status === 'deleted' ? initialEntry : await autosave.flush(); await gql('mutation($id:ID!,$number:Int!,$version:Int!){restoreEntry(id:$id,number:$number,version:$version){id}}', { id: saved!.id, number, version: saved!.version }); onSaved('Revision restored as a draft.') }
    catch (reason) { setError(message(reason)) }
    finally { setBusy(false) }
  }
  async function publicationAction(action: 'unpublishEntry' | 'cancelSchedule') {
    if (!entry) return
    setBusy(true); setError('')
    try {
      const saved = await autosave.flush()
      await gql(`mutation($id:ID!,$version:Int!){${action}(id:$id,version:$version){id}}`, { id: saved!.id, version: saved!.version })
      onSaved(action === 'unpublishEntry' ? 'Entry unpublished. Draft and history retained.' : 'Schedule cancelled. Live content preserved.')
    } catch (reason) { setError(message(reason)) }
    finally { setBusy(false) }
  }
  return <Dialog title={entry ? entry.title : creationLabels[key] || 'New entry'} open onClose={close}>
    <form className="editor-form" onSubmit={save}>
      <div className="editor-meta"><span className={`content-type-label ${key}`}><FileText size={13} />{definition.name}</span>{entry && <><Badge>{entry.status === 'deleted' ? 'Trash' : entry.isLive ? 'Live' : 'Unpublished'}</Badge>{entry.hasUnpublishedChanges && entry.status !== 'deleted' && <Badge>Unpublished changes</Badge>}<small>Version {entry.version}</small><Button type="button" variant="outline" disabled={busy} onClick={loadHistory}>History & restore</Button></>}</div>
      {editable && <div role="status">Draft: {autosave.state}{autosave.state === 'Incomplete' && ' — complete the slug and required fields to autosave.'}</div>}
      {autosave.error && <div className="form-error" role="alert">{autosave.error}<Button type="button" variant="outline" onClick={autosave.state === 'Conflict' ? autosave.compare : autosave.retry}>{autosave.state === 'Conflict' ? 'Compare server version' : 'Check and retry'}</Button></div>}
      {autosave.server && <section><h3>Server version {autosave.server.version}</h3><pre>{JSON.stringify(autosave.server.data,null,2)}</pre><p>Your edits remain in the form above. Copy any changes you want to keep before reloading.</p><Button type="button" onClick={() => { if (confirmClose()) {const next=autosave.reload();if(next){setData(next.data);setSlug(next.slug);setKey(next.typeKey);setStatus('draft')}} }}>Discard local edits and reload server</Button></section>}
      <fieldset disabled={!editable || busy || initialEntry?.status === 'deleted'}>
        {!entry && <label>Content type<select value={key} onChange={event => { setKey(event.target.value); setData(dataForType(types.find(t => t.key === event.target.value)!)) }}>{types.map(t => <option key={t.key} value={t.key}>{t.name}</option>)}</select></label>}
        <section className="publishing-panel" aria-label="Publishing options">
          <div className="publishing-title"><CalendarClock size={16} /><strong>Publishing</strong></div>
          <div className="publishing-options" role="group" aria-label="Publishing status">{[
            { value: 'draft', label: 'Save draft', description: 'Preserve live content and schedule' },
            { value: 'published', label: 'Publish now', description: 'Make it available' },
            { value: 'scheduled', label: entry?.scheduledAt ? 'Replace schedule' : 'Schedule', description: 'Capture these edits for later' },
          ].map(option => <button type="button" key={option.value} className={status === option.value ? 'selected' : ''} aria-pressed={status === option.value} onClick={() => setStatus(option.value)}><span>{option.label}{status === option.value && <Check size={12} />}</span><small>{option.description}</small></button>)}</div>
          {status === 'scheduled' ? <div className="schedule-fields"><label>Publish on<input type="datetime-local" required min={localDateTime(new Date(Date.now() + 60000))} value={schedule} onChange={event => setSchedule(event.target.value)} /></label><p className="field-help">Timezone: <strong>{timezone}</strong>. This captures the selected draft. Later draft edits will not change it. Existing live content stays available.</p></div> : <p className="field-help">{status === 'published' ? 'Publishing makes this entry available to your connected frontends.' : 'Draft saves preserve existing live content and any pending schedule.'}</p>}
          {entry?.scheduledAt && <p className="field-help">Scheduled revision {entry.scheduledRevision} for {timestamp(entry.scheduledAt)} ({timezone}). {entry.scheduledRevision !== entry.version && 'Newer draft changes are not scheduled. Use Replace schedule to include them.'}</p>}
          {entry?.scheduleError && <p className="form-error" role="alert">Publication failed: {entry.scheduleError.message} Resolve the cause and schedule again.</p>}
          {editable && entry?.scheduledAt && <Button type="button" variant="outline" onClick={() => publicationAction('cancelSchedule')}>Cancel schedule</Button>}
          {editable && entry?.isLive && <Button type="button" variant="outline" onClick={() => publicationAction('unpublishEntry')}>Unpublish</Button>}
        </section>
        <label>Slug<input required maxLength={220} value={slug} onChange={event => { setSlugEdited(true); setSlug(slugify(event.target.value)) }} /></label>
        {fields.map(field => <FieldInput key={field.name} field={field} value={data[field.name]} onChange={value => { setData(old => ({ ...old, [field.name]: value })); if (field.name === 'title' && !slugEdited) { const title = typeof value === 'string' ? value : value && typeof value === 'object' ? Object.values(value)[0] : ''; setSlug(slugify(String(title || ''))) } }} references={references} assets={assets} />)}
      </fieldset>
      {history && <section className="revision-list"><h3>History</h3>{history.map(revision => <article key={revision.number}><div className="inline-form"><strong>Version {revision.number}</strong><small>{revision.author} · {new Date(revision.createdAt).toLocaleString()}</small>{editable && <Button type="button" variant="outline" disabled={busy} onClick={() => restore(revision.number)}>Restore draft</Button>}</div><details><summary>Preview this revision</summary><pre>{JSON.stringify(revision.snapshot, null, 2)}</pre></details></article>)}</section>}
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="modal-actions"><Button type="button" variant="outline" disabled={busy} onClick={close}>Close</Button>{editable && initialEntry?.status !== 'deleted' && <Button type="submit" disabled={busy}>{busy ? 'Saving…' : status === 'published' ? 'Publish now' : status === 'scheduled' ? 'Schedule publication' : 'Save draft'}</Button>}</div>
    </form>
  </Dialog>
}

export function Content({ types, role, onChanged }: { types: ContentType[]; role: string; onChanged: () => void }) {
  const [page, setPage] = useState<Page>({ nodes: [], total: 0, endCursor: null, hasNextPage: false })
  const [groups, setGroups] = useState<Group[]>([])
  const [filter, setFilter] = useState('')
  const [search, setSearch] = useState('')
  const [type, setType] = useState('')
  const [status, setStatus] = useState('')
  const [sort, setSort] = useState('updated_desc')
  const [cursors, setCursors] = useState<(string | null)[]>([null])
  const [selected, setSelected] = useState<string[]>([])
  const [editor, setEditor] = useState<Entry | null | undefined>()
  const [deleting, setDeleting] = useState<Entry[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [refresh, setRefresh] = useState(0)
  const editable = role !== 'reader'
  const selectedType = types.find(item => item.key === type)
  const groupList = [...groups].sort((a, b) => {
    const rank = (key: string) => typeOrder.includes(key) ? typeOrder.indexOf(key) : 99
    return rank(a.key) - rank(b.key) || a.name.localeCompare(b.name)
  })
  useEffect(() => { const timer = setTimeout(() => setSearch(filter), 250); return () => clearTimeout(timer) }, [filter])
  useEffect(() => { setCursors([null]); setSelected([]) }, [search, type, status, sort])
  useEffect(() => {
    // Refresh scheduled rows when the server publishes them, without losing an open editor.
    const timer = setInterval(() => { if (document.visibilityState === 'visible' && editor === undefined) setRefresh(old => old + 1) }, 10000)
    return () => clearInterval(timer)
  }, [editor])
  useEffect(() => {
    let alive = true; setBusy(true); setError('')
    gql<{ entries: Page; contentGroups: Group[] }>(`query($type:String,$status:String,$search:String!,$sort:String!,$after:String){entries(typeKey:$type,status:$status,search:$search,sort:$sort,first:20,after:$after){nodes{${entryFields}} total endCursor hasNextPage} contentGroups(status:$status)}`, { type: type || null, status: status || null, search, sort, after: cursors[cursors.length - 1] }).then(result => { if (alive) { setPage(result.entries); setGroups(result.contentGroups); setSelected(old => old.filter(id => result.entries.nodes.some(entry => entry.id === id))) } }).catch(reason => { if (alive) setError(message(reason)) }).finally(() => { if (alive) setBusy(false) })
    return () => { alive = false }
  }, [type, status, search, sort, cursors, refresh])
  async function remove() {
    setBusy(true)
    try { for (const entry of deleting!) await gql('mutation($id:ID!,$version:Int!){deleteEntry(id:$id,version:$version)}', { id: entry.id, version: entry.version }); setNotice('Entries moved to trash. Restore them from revision history.'); setDeleting(null); onChanged() }
    catch (reason) { setError(message(reason)) }
    finally { setBusy(false); setRefresh(old => old + 1) }
  }
  return <>
    <div className="page-heading"><div><div className="eyebrow">CONTENT LIBRARY</div><h1>{selectedType?.name || 'Content'}</h1><p className="subtitle">Organize content by type. Publish now or plan ahead.</p></div>{editable && <Button disabled={!types.length} onClick={() => setEditor(null)}><Plus size={16} />{creationLabels[type] || 'New entry'}</Button>}</div>
    {!types.length && <p className="notice">Create a content type first in <a href="#types">Content types</a>.</p>}
    <div className="content-groups" role="group" aria-label="Content groups">
      <button className={!type ? 'selected' : ''} aria-pressed={!type} onClick={() => setType('')}><FileText size={15} />All content<span>{groups.reduce((total, group) => total + group.count, 0)}</span></button>
      {groupList.map(group => { const Icon = typeIcons[group.key as keyof typeof typeIcons] || FileText; return <button key={group.key} className={type === group.key ? 'selected' : ''} aria-pressed={type === group.key} onClick={() => setType(group.key)}><Icon size={15} />{group.name}<span>{group.count}</span></button> })}
    </div>
    {notice && <p className="notice" role="status">{notice}</p>}{error && <p className="form-error" role="alert">{error}</p>}
    <section className="entries-panel">
      <div className="panel-heading"><h2>{selectedType?.name || 'All entries'} <span className="entry-total">{page.total}</span></h2><select aria-label="Content type" value={type} onChange={event => setType(event.target.value)}><option value="">All content types</option>{types.map(item => <option key={item.key} value={item.key}>{item.name}</option>)}</select></div>
      <div className="table-toolbar"><label className="searchbox"><Search size={16} /><input aria-label="Search entries" placeholder="Search entries…" value={filter} onChange={event => setFilter(event.target.value)} /></label><select aria-label="Publishing status" value={status} onChange={event => setStatus(event.target.value)}><option value="">Active entries</option><option value="draft">Draft</option><option value="published">Published</option><option value="scheduled">Scheduled</option><option value="deleted">Trash</option></select><select aria-label="Sort entries" value={sort} onChange={event => setSort(event.target.value)}><option value="updated_desc">Newest first</option><option value="updated_asc">Oldest first</option><option value="title_asc">Title A–Z</option><option value="title_desc">Title Z–A</option></select>{selected.length > 0 && editable && status !== 'deleted' && <Button variant="outline" onClick={() => setDeleting(page.nodes.filter(entry => selected.includes(entry.id)))}>Trash {selected.length}</Button>}</div>
      <div className="table-scroll"><table><thead><tr><th className="check-cell"><input type="checkbox" aria-label="Select all entries" checked={page.nodes.length > 0 && selected.length === page.nodes.length} onChange={event => setSelected(event.target.checked ? page.nodes.map(row => row.id) : [])} /></th><th>TITLE</th><th>TYPE</th><th>STATUS / PUBLISHING</th><th>UPDATED</th><th>ACTIONS</th></tr></thead><tbody>
        {busy && !page.nodes.length ? <tr><td colSpan={6} className="empty-state">Loading entries…</td></tr> : page.nodes.map(entry => {
          const Icon = typeIcons[entry.typeKey as keyof typeof typeIcons] || FileText
          return <tr key={entry.id}><td className="check-cell"><input type="checkbox" aria-label={`Select ${entry.title}`} checked={selected.includes(entry.id)} onChange={event => setSelected(old => event.target.checked ? [...old, entry.id] : old.filter(id => id !== entry.id))} /></td><td><button className="title-cell text-button" onClick={() => setEditor(entry)}><div className={`doc-icon ${entry.typeKey}`}><Icon size={15} /></div><div><strong>{entry.title}</strong><span className="entry-slug">/{entry.slug}</span></div></button></td><td><span className={`content-type-label ${entry.typeKey}`}>{types.find(item => item.key === entry.typeKey)?.name || entry.typeKey}</span></td><td><div className="publishing-cell"><Badge className={entry.isLive ? 'published' : entry.status}><span />{entry.status === 'deleted' ? 'Trash' : entry.isLive ? 'Live' : 'Unpublished'}</Badge>{entry.hasUnpublishedChanges && entry.status !== 'deleted' && <small>Unpublished changes</small>}{entry.scheduledAt && <small>Scheduled revision {entry.scheduledRevision}</small>}{entry.scheduleError && <small role="status">Publication failed</small>}{entry.scheduledAt && <span className="scheduled-date" title={`${timestamp(entry.scheduledAt)} (${Intl.DateTimeFormat().resolvedOptions().timeZone})`}><CalendarClock size={12} /><time dateTime={entry.scheduledAt}>{timestamp(entry.scheduledAt)}</time></span>}</div></td><td className="updated">{new Date(entry.updatedAt).toLocaleDateString()}</td><td><div className="row-actions"><button className="text-button" onClick={() => setEditor(entry)}>{editable ? entry.status === 'deleted' ? 'Restore' : 'Edit' : 'View'}</button>{editable && entry.status !== 'deleted' && <button className="text-button muted" onClick={() => setDeleting([entry])}>Trash</button>}</div></td></tr>
        })}
        {!busy && page.total === 0 && <tr><td className="empty-state" colSpan={6}>No matching entries.</td></tr>}
      </tbody></table></div>
      <footer className="table-footer"><span>{busy ? 'Refreshing…' : `${page.total} entries · page ${cursors.length}`}</span><div className="pagination"><Button variant="outline" disabled={cursors.length === 1 || busy} onClick={() => setCursors(old => old.slice(0, -1))}>Previous</Button><Button variant="outline" disabled={!page.hasNextPage || busy} onClick={() => setCursors(old => [...old, page.endCursor])}>Next</Button></div></footer>
    </section>
    {editor !== undefined && types.length > 0 && <EntryEditor entry={editor} initialType={type} types={types} editable={editable} onClose={() => setEditor(undefined)} onSaved={text => { setNotice(text); setEditor(undefined); setRefresh(old => old + 1); onChanged() }} />}
    {deleting && <Dialog title="Move entries to trash?" open onClose={() => setDeleting(null)}><p>{deleting.map(entry => entry.title).join(', ')} will stop appearing in delivery queries. You can restore entries from their history.</p><div className="modal-actions"><Button variant="outline" onClick={() => setDeleting(null)}>Cancel</Button><Button disabled={busy} onClick={remove}>Move to trash</Button></div></Dialog>}
  </>
}
