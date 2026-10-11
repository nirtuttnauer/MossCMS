import { useEffect, useId, useRef, useState } from 'react'
import { CalendarClock, FileText, Folder, Image, NotebookPen, Plus, Search, Settings2 } from 'lucide-react'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Dialog } from '../components/ui/dialog'
import { confirmNavigation, useUnsavedChanges } from '../lib/unsaved'
import { contentHash, readContentRoute, setContentRoute } from '../lib/navigation'
import { getContext, entryByIdQuery, entryFields, gql, message, type ContentType, type Entry } from '../lib/api'
import { creationLabels, timestamp, typeOrder, type DuplicationSource, type EntryPage as Page } from '../lib/entries'
import { trashEntry, type TrashResult } from '../lib/bulkTrash'
import { EntryEditor } from './EntryEditor'

type Group = { key: string; name: string; count: number }
const typeIcons = { siteProject: Folder, sitePost: NotebookPen, sitePage: FileText, siteSlide: Image, siteProfile: Settings2 }

export function Content({ types, role, onChanged, projectId, defaultLocale = 'en', locales = ['en'] }: { types: ContentType[]; role: string; onChanged: () => void; projectId?: string; defaultLocale?: string; locales?: string[] }) {
  const initialRoute = readContentRoute(types)
  const acceptedHash = useRef(location.hash)
  const loadId = useRef(0)
  const listScroll = useRef(0)
  const listHeading = useRef<HTMLHeadingElement>(null)
  const trashActionId = useId()
  const recoverTrashFocus = useRef(false)
  const context = useRef(getContext()).current
  const setHashParams = (updater: (params: URLSearchParams) => void, push = false) => {
    const route = readContentRoute(types)
    const params = new URLSearchParams(contentHash(route).split('?')[1] || '')
    updater(params)
    setContentRoute({ ...readContentRoute(types, `#content?${params}`), workspace: projectId || context.project || route.workspace }, push)
    acceptedHash.current = location.hash
  }
  const [page, setPage] = useState<Page>({ nodes: [], total: 0, endCursor: null, hasNextPage: false })
  const [groups, setGroups] = useState<Group[]>([])
  const [filter, setFilter] = useState(initialRoute.search)
  const [search, setSearch] = useState(initialRoute.search)
  const [type, setType] = useState(initialRoute.type)
  const [status, setStatus] = useState(initialRoute.status)
  const [sort, setSort] = useState(initialRoute.sort)
  const [cursors, setCursors] = useState<(string | null)[]>([null])
  const [selected, setSelected] = useState<string[]>([])
  const [editor, setEditor] = useState<Entry | null | undefined>()
  const [seed, setSeed] = useState<DuplicationSource | null>(null)
  const [deleting, setDeleting] = useState<Entry[] | null>(null)
  const [trash, setTrash] = useState<TrashResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [trashBusy, setTrashBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [refresh, setRefresh] = useState(0)
  useUnsavedChanges(trashBusy)
  useEffect(() => {
    if (trashBusy || !recoverTrashFocus.current) return
    recoverTrashFocus.current = false
    // Disabled actions lose keyboard focus in Safari; wait for controls and Radix close cleanup.
    const frame = requestAnimationFrame(() => {
      if (getContext().project !== context.project) return
      if (deleting) document.getElementById(trashActionId)?.focus()
      else listHeading.current?.focus()
    })
    return () => cancelAnimationFrame(frame)
  }, [trashBusy, deleting, context, trashActionId])
  const editable = role !== 'reader'
  const selectedType = types.find(item => item.key === type)
  const groupList = [...groups].sort((a, b) => {
    const rank = (key: string) => typeOrder.includes(key) ? typeOrder.indexOf(key) : 99
    return rank(a.key) - rank(b.key) || a.name.localeCompare(b.name)
  })
  useEffect(() => { const timer = setTimeout(() => setSearch(filter), 250); return () => clearTimeout(timer) }, [filter])
  useEffect(() => { setCursors([null]); setSelected([]) }, [search, type, status, sort])

  useEffect(() => {
    setHashParams(params => {
      if (type) params.set('type', type); else params.delete('type')
      if (status) params.set('status', status); else params.delete('status')
      if (search) params.set('search', search); else params.delete('search')
      if (sort && sort !== 'updated_desc') params.set('sort', sort); else params.delete('sort')
    }, false)
  }, [type, status, search, sort])

  const openEntry = (item: Entry | null) => {
    listScroll.current = window.scrollY
    setSeed(null)
    setEditor(item)
    setHashParams(p => p.set('entry', item?.id || 'new'), true)
  }

  const closeEditor = () => {
    setSeed(null)
    setEditor(undefined)
    setHashParams(p => p.delete('entry'), true)
    requestAnimationFrame(() => window.scrollTo(0, listScroll.current))
  }

  const duplicateEntry = (item: Entry) => {
    if (!editable || !confirmNavigation()) return
    const copiedData = JSON.parse(JSON.stringify(item.data || {}))
    if (typeof copiedData.title === 'string') {
      copiedData.title = `${copiedData.title} (Copy)`
    } else if (copiedData.title && typeof copiedData.title === 'object') {
      const loc = { ...(copiedData.title as Record<string, unknown>) }
      const locale = defaultLocale in loc ? defaultLocale : Object.keys(loc)[0]
      if (locale) loc[locale] = `${loc[locale] || ''} (Copy)`
      copiedData.title = loc
    }
    const suggestedSlug = `${item.slug.slice(0, 200).replace(/-+$/, '')}-copy-${crypto.randomUUID().slice(0, 8)}`
    setSeed({
      id: item.id,
      title: item.title,
      version: item.version,
      typeKey: item.typeKey,
      slug: suggestedSlug,
      data: copiedData,
    })
    setEditor(null)
    setHashParams(p => p.set('entry', 'new'), true)
  }

  const copyEntryLink = async (item: Entry) => {
    const route = readContentRoute(types)
    const link = `${location.origin}${location.pathname}${contentHash({ ...route, entry: item.id, workspace: projectId || context.project || route.workspace })}`
    try {
      await navigator.clipboard.writeText(link)
      setNotice('Entry link copied to clipboard.')
    } catch {
      setNotice(`Copy this link: ${link}`)
    }
  }

  useEffect(() => {
    let alive = true
    const syncFromUrl = (event?: Event) => {
      if (event && !event.type.startsWith('moss:') && location.hash !== acceptedHash.current && !confirmNavigation()) {
        history.replaceState(null, '', acceptedHash.current)
        return
      }
      acceptedHash.current = location.hash
      const route = readContentRoute(types)
      if (route.workspace && projectId && route.workspace !== projectId) return
      setType(route.type); setStatus(route.status); setFilter(route.search); setSearch(route.search); setSort(route.sort)
      const request = ++loadId.current
      if (!route.entry) { setSeed(null); setEditor(undefined); return }
      if (route.entry === 'new') { setEditor(null); return }
      if (editor?.id === route.entry) return
      setSeed(null)
      // Always load by ID: a filtered page may be stale or exclude this entry.
      gql<{ entry: Entry | null }>(entryByIdQuery, { id: route.entry }, context)
        .then(result => {
          if (!alive || request !== loadId.current) return
          if (result.entry && types.some(type => type.key === result.entry!.typeKey)) { setEditor(result.entry); setError('') }
          else { setError('Entry not found or access denied.'); setEditor(undefined); setHashParams(p => p.delete('entry')) }
        }).catch(() => {
          if (!alive || request !== loadId.current) return
          setError('Entry not found or access denied.'); setEditor(undefined); setHashParams(p => p.delete('entry'))
        })
    }
    syncFromUrl()
    window.addEventListener('hashchange', syncFromUrl)
    window.addEventListener('popstate', syncFromUrl)
    window.addEventListener('moss:navigationaccepted', syncFromUrl)
    return () => {
      alive = false
      window.removeEventListener('hashchange', syncFromUrl)
      window.removeEventListener('popstate', syncFromUrl)
      window.removeEventListener('moss:navigationaccepted', syncFromUrl)
    }
  }, [types, projectId, editor?.id])
  useEffect(() => {
    // Refresh scheduled rows when the server publishes them, without losing an open editor.
    const timer = setInterval(() => { if (document.visibilityState === 'visible' && editor === undefined && !deleting) setRefresh(old => old + 1) }, 10000)
    return () => clearInterval(timer)
  }, [editor, deleting])
  useEffect(() => {
    let alive = true; setBusy(true); setError('')
    gql<{ entries: Page; contentGroups: Group[] }>(`query($type:String,$status:String,$search:String!,$sort:String!,$after:String){entries(typeKey:$type,status:$status,search:$search,sort:$sort,first:20,after:$after){nodes{${entryFields}} total endCursor hasNextPage} contentGroups(status:$status)}`, { type: type || null, status: status || null, search, sort, after: cursors[cursors.length - 1] }, context).then(result => { if (alive) { setPage(result.entries); setGroups(result.contentGroups); setSelected(old => old.filter(id => result.entries.nodes.some(entry => entry.id === id))) } }).catch(reason => { if (alive) { if (cursors.length > 1) setCursors([null]); else setError(message(reason)) } }).finally(() => { if (alive) setBusy(false) })
    return () => { alive = false }
  }, [type, status, search, sort, cursors, refresh])
  async function remove(items: Entry[]) {
    if (trashBusy) return
    recoverTrashFocus.current = Boolean(document.activeElement?.closest('[role="dialog"]'))
    setTrashBusy(true); setError('')
    const results: TrashResult = trash && items.every(entry => entry.id in trash.results) ? { ...trash, results: { ...trash.results } } : { total: items.length, results: Object.fromEntries(items.map(entry => [entry.id, { outcome: 'pending' as const }])) }
    setTrash(results)
    for (let i = 0; i < items.length; i++) {
      if (getContext().project !== context.project) {
        for (const item of items.slice(i)) results.results[item.id] = { outcome: 'not_attempted', reason: 'Workspace changed. Return to the original workspace to retry.' }
        break
      }
      const entry = items[i]
      if (results.results[entry.id]?.outcome === 'done') continue
      const version = results.results[entry.id]?.version ?? entry.version
      const outcome = await trashEntry({ ...entry, version }, Boolean(trash), context)
      results.results[entry.id] = outcome
      results.results = { ...results.results }
      setTrash({ ...results })
      if (outcome.outcome !== 'done') {
        for (let j = i + 1; j < items.length; j++) {
          const nextId = items[j].id
          if (results.results[nextId]?.outcome !== 'done') {
            results.results[nextId] = { outcome: 'not_attempted' }
          }
        }
        results.results = { ...results.results }
        setTrash({ ...results })
        break
      }
    }
    const unresolved = items.filter(entry => results.results[entry.id]?.outcome !== 'done')
    const done = items.length - unresolved.length
    setDeleting(unresolved.length ? unresolved.map(entry => ({ ...entry, version: results.results[entry.id]?.version ?? entry.version })) : null)
    setSelected(old => old.filter(id => unresolved.some(entry => entry.id === id)))
    if (!unresolved.length) {
      setNotice(`${results.total} ${results.total === 1 ? 'entry' : 'entries'} moved to trash. Restore them from revision history.`)
      setTrash(null)
      onChanged()
    } else if (done) {
      onChanged()
    }
    setTrashBusy(false); setRefresh(old => old + 1)
  }
  if (editor !== undefined && types.length > 0) return <>{notice && <p className="notice" role="status">{notice}</p>}<EntryEditor key={editor?.id || (seed ? `copy-${seed.id}` : 'new')} entry={editor} seed={seed} initialType={type} types={types} projectId={projectId} defaultLocale={defaultLocale} locales={locales} editable={editable} role={role} onClose={closeEditor} onSaved={text => { setNotice(text); setSeed(null); closeEditor(); setRefresh(old => old + 1); onChanged() }} onCopyLink={copyEntryLink} onDuplicate={duplicateEntry} /></>
  return <>
    <div className="page-heading"><div><div className="eyebrow">CONTENT LIBRARY</div><h1 ref={listHeading} tabIndex={-1}>{selectedType?.name || 'Content'}</h1><p className="subtitle">Organize content by type. Publish now or plan ahead.</p></div>{editable && <Button disabled={!types.length} onClick={() => openEntry(null)}><Plus size={16} />{creationLabels[type] || 'New entry'}</Button>}</div>
    {!types.length && <p className="notice">Create a content type first in <a href="#types">Content types</a>.</p>}
    <div className="content-groups" role="group" aria-label="Content groups">
      <button className={!type ? 'selected' : ''} aria-pressed={!type} onClick={() => setType('')}><FileText size={15} />All content<span>{groups.reduce((total, group) => total + group.count, 0)}</span></button>
      {groupList.map(group => { const Icon = typeIcons[group.key as keyof typeof typeIcons] || FileText; return <button key={group.key} className={type === group.key ? 'selected' : ''} aria-pressed={type === group.key} onClick={() => setType(group.key)}><Icon size={15} />{group.name}<span>{group.count}</span></button> })}
    </div>
    {notice && <p className="notice" role="status">{notice}{notice.includes('moved to trash') && <> <button type="button" className="text-button" onClick={() => setStatus('deleted')}>View trash</button></>}</p>}{error && <p className="form-error" role="alert">{error}</p>}
    <section className="entries-panel" aria-label="Entries">
      <div className="panel-heading"><h2>{selectedType?.name || 'All entries'} <span className="entry-total">{page.total}</span></h2><select aria-label="Content type" value={type} onChange={event => setType(event.target.value)}><option value="">All content types</option>{types.map(item => <option key={item.key} value={item.key}>{item.name}</option>)}</select></div>
      <div className="table-toolbar"><label className="searchbox"><Search size={16} /><input aria-label="Search entries" placeholder="Search entries…" value={filter} onChange={event => setFilter(event.target.value)} /></label><select aria-label="Publishing status" value={status} onChange={event => setStatus(event.target.value)}><option value="">Active entries</option><option value="draft">Draft</option><option value="published">Published</option><option value="scheduled">Scheduled</option><option value="deleted">Trash</option></select><select aria-label="Sort entries" value={sort} onChange={event => setSort(event.target.value)}><option value="updated_desc">Newest first</option><option value="updated_asc">Oldest first</option><option value="title_asc">Title A–Z</option><option value="title_desc">Title Z–A</option></select>{selected.length > 0 && editable && status !== 'deleted' && <Button variant="outline" onClick={() => setDeleting(page.nodes.filter(entry => selected.includes(entry.id)))}>Trash {selected.length}</Button>}</div>
      <div className="table-scroll"><table className="content-table"><thead><tr><th className="check-cell"><input type="checkbox" aria-label="Select all entries" checked={page.nodes.length > 0 && selected.length === page.nodes.length} onChange={event => setSelected(event.target.checked ? page.nodes.map(row => row.id) : [])} /></th><th>TITLE</th><th>TYPE</th><th>STATUS / PUBLISHING</th><th>UPDATED</th><th>ACTIONS</th></tr></thead><tbody>
        {busy && !page.nodes.length ? <tr><td colSpan={6} className="empty-state">Loading entries…</td></tr> : page.nodes.map(entry => {
          const Icon = typeIcons[entry.typeKey as keyof typeof typeIcons] || FileText
          return <tr key={entry.id}><td className="check-cell"><input type="checkbox" aria-label={`Select ${entry.title}`} checked={selected.includes(entry.id)} onChange={event => setSelected(old => event.target.checked ? [...old, entry.id] : old.filter(id => id !== entry.id))} /></td><td><button className="title-cell text-button" onClick={() => openEntry(entry)}><div className={`doc-icon ${entry.typeKey}`}><Icon size={15} /></div><div><strong>{entry.title}</strong><span className="entry-slug">/{entry.slug}</span></div></button></td><td><span className={`content-type-label ${entry.typeKey}`}>{types.find(item => item.key === entry.typeKey)?.name || entry.typeKey}</span></td><td><div className="publishing-cell"><Badge className={entry.isLive ? 'published' : entry.status}><span />{entry.status === 'deleted' ? 'Trash' : entry.isLive ? 'Live' : 'Unpublished'}</Badge>{entry.hasUnpublishedChanges && entry.status !== 'deleted' && <small>Unpublished changes</small>}{entry.scheduledAt && <small>Scheduled revision {entry.scheduledRevision}</small>}{entry.scheduleError && <small role="status">Publication failed</small>}{entry.scheduledAt && <span className="scheduled-date" title={`${timestamp(entry.scheduledAt)} (${Intl.DateTimeFormat().resolvedOptions().timeZone})`}><CalendarClock size={12} /><time dateTime={entry.scheduledAt}>{timestamp(entry.scheduledAt)}</time></span>}</div></td><td className="updated"><time dateTime={entry.updatedAt} title={timestamp(entry.updatedAt)}>{new Date(entry.updatedAt).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}</time></td><td><div className="row-actions"><button className="text-button" onClick={() => openEntry(entry)}>{editable ? entry.status === 'deleted' ? 'Restore' : 'Edit' : 'View'}</button><button className="text-button" onClick={() => copyEntryLink(entry)} title="Copy entry link">Copy link</button>{editable && entry.status !== 'deleted' && <button className="text-button" disabled={busy} onClick={() => duplicateEntry(entry)} title="Duplicate entry">Duplicate</button>}{editable && entry.status !== 'deleted' && <button className="text-button destructive-text" onClick={() => setDeleting([entry])}>Trash</button>}</div></td></tr>
        })}
        {!busy && page.total === 0 && <tr><td className="empty-state" colSpan={6}><div className="empty-content"><Search size={28} aria-hidden="true" /><h3>{filter || status ? 'No matching entries' : 'Your library starts here'}</h3><p>{filter || status ? 'Try another search or publishing status.' : 'Create your first entry to start building your content library.'}</p>{filter || status ? <Button variant="outline" onClick={() => { setFilter(''); setStatus('') }}>Clear search and status</Button> : editable && types.length > 0 && <Button onClick={() => openEntry(null)}><Plus size={16} aria-hidden="true" />{creationLabels[type] || 'New entry'}</Button>}</div></td></tr>}
      </tbody></table></div>
      <footer className="table-footer"><span>{busy ? 'Refreshing…' : `${page.total} ${page.total === 1 ? "entry" : "entries"} · page ${cursors.length}`}</span><div className="pagination"><Button variant="outline" disabled={cursors.length === 1 || busy} onClick={() => setCursors(old => old.slice(0, -1))}>Previous</Button><Button variant="outline" disabled={!page.hasNextPage || busy} onClick={() => setCursors(old => [...old, page.endCursor])}>Next</Button></div></footer>
    </section>

    {deleting && <Dialog title={trash ? "Trash results and retry" : "Move entries to trash?"} open onClose={() => { if (!trashBusy) { setDeleting(null); setTrash(null) } }}>
      {deleting.some(e => e.isLive || e.scheduledAt) && <p className="notice" role="alert">Moving live or scheduled content to trash unpublishes it immediately and cancels upcoming schedules.</p>}
      {trash ? (() => {
        const completed = Object.values(trash.results).filter(r => r.outcome === 'done').length
        const failed = Object.values(trash.results).filter(r => r.outcome === 'failed').length
        const uncertain = Object.values(trash.results).filter(r => r.outcome === 'uncertain').length
        const notAttempted = Object.values(trash.results).filter(r => r.outcome === 'not_attempted' || r.outcome === 'pending').length
        return (
          <div className="trash-result-details" role="status" aria-live="polite">
            <p><strong>{completed} completed, {failed} failed, {notAttempted} not attempted{uncertain > 0 && `, ${uncertain} unconfirmed`}</strong></p>
            {Object.entries(trash.results).filter(([_, r]) => r.outcome === 'failed' || r.outcome === 'uncertain').map(([id, r]) => {
              const entry = page.nodes.find(e => e.id === id) || deleting.find(e => e.id === id)
              return <p key={id} className="form-error" role="alert">{entry?.title || id}: {r.reason || 'Failed to move to trash'}</p>
            })}
            <p>You can retry the {deleting.length} unresolved {deleting.length === 1 ? 'entry' : 'entries'}, or review them in <button disabled={trashBusy} type="button" className="text-button" onClick={() => { setDeleting(null); setTrash(null); setStatus('deleted'); }}>Trash</button>.</p>
          </div>
        )
      })() : (
        <p>{deleting.map(entry => entry.title).join(', ')} will stop appearing in delivery queries. Pending schedules are canceled. You can restore entries from <button disabled={trashBusy} type="button" className="text-button" onClick={() => { setDeleting(null); setTrash(null); setStatus('deleted'); }}>Trash</button> or revision history.</p>
      )}
      <div className="modal-actions">
        <Button disabled={trashBusy} variant="outline" onClick={() => { setDeleting(null); setTrash(null) }}>Cancel</Button>
        <Button id={trashActionId} disabled={trashBusy} onClick={() => remove(deleting)}>{trash ? 'Retry unresolved entries' : 'Move to trash'}</Button>
      </div>
    </Dialog>}
  </>
}
