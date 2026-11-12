import { useEffect, useState, type FormEvent } from 'react'
import { Button } from '../components/ui/button'
import { can } from '../lib/access'
import { gql, message } from '../lib/api'

type ReleaseItem = {
  id: string
  entryId: string
  action: string
  revision: number
  slug: string
  title: string
  schemaVersion: number
}
type ReleaseRecord = {
  id: string
  name: string
  status: string
  scheduledAt: string | null
  error: { message?: string } | null
  version: number
  items: ReleaseItem[]
}

export function Releases({ role }: { role: string }) {
  const [releases, setReleases] = useState<ReleaseRecord[]>([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const allowPublish = can(role, 'publish')
  const allowSchedule = can(role, 'schedule')
  async function load() {
    setLoading(true)
    setError('')
    try {
      const result = await gql<{ releases: ReleaseRecord[] }>('{releases}')
      setReleases(result.releases)
    } catch (reason) {
      setError(message(reason))
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => { void load() }, [])
  async function run(key: string, action: () => Promise<ReleaseRecord | void>) {
    setBusy(key)
    setError('')
    setNotice('')
    try {
      const next = await action()
      if (next) setReleases(current => [next, ...current.filter(item => item.id !== next.id)])
      else await load()
      setNotice('Release updated.')
    } catch (reason) {
      setError(message(reason))
    } finally {
      setBusy('')
    }
  }
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const name = String(new FormData(form).get('name') || '')
    await run('create', async () => {
      const result = await gql<{ createRelease: ReleaseRecord }>('mutation($name:String!){createRelease(name:$name)}', { name })
      form.reset()
      return result.createRelease
    })
  }
  async function add(release: ReleaseRecord, event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const body = Object.fromEntries(new FormData(event.currentTarget))
    await run(release.id, async () => {
      const result = await gql<{ addReleaseEntry: ReleaseRecord }>(
        'mutation($id:ID!,$entryId:ID!,$action:String!,$version:Int!){addReleaseEntry(id:$id,entryId:$entryId,action:$action,version:$version)}',
        { id: release.id, entryId: body.entryId, action: body.action, version: release.version },
      )
      return result.addReleaseEntry
    })
  }
  function mutate(release: ReleaseRecord, key: string, query: string, variables: Record<string, unknown>) {
    return run(`${key}:${release.id}`, async () => {
      const result = await gql<Record<string, ReleaseRecord>>(query, variables)
      return result[key]
    })
  }

  return <>
    <div className="page-heading"><div><div className="eyebrow">SHIP TOGETHER</div><h1>Releases</h1><p className="subtitle">Capture approved revisions and publish every action in the set, or leave live content unchanged.</p></div></div>
    {error && <p className="form-error" role="alert">{error} <Button variant="outline" onClick={() => { void load() }}>Retry releases</Button></p>}
    {notice && <p className="notice" role="status">{notice}</p>}
    {loading && <p role="status">Loading releases…</p>}
    {allowPublish && <section className="plain-card"><h2>New release</h2><form className="inline-form" onSubmit={create}><input name="name" required maxLength={100} aria-label="Release name" placeholder="Spring launch" disabled={Boolean(busy)} /><Button type="submit" disabled={Boolean(busy)}>{busy === 'create' ? 'Creating release…' : 'Create release'}</Button></form></section>}
    {releases.map(release => <article className="plain-card" key={release.id} aria-label={release.name}>
      <h2>{release.name}</h2>
      <p>Status: {release.status}{release.scheduledAt ? ` · scheduled ${new Date(release.scheduledAt).toLocaleString()}` : ''}</p>
      {release.error?.message && <p className="form-error" role="alert">{release.error.message}</p>}
      {release.items.length ? <div className="table-scroll"><table><thead><tr><th>ENTRY</th><th>ACTION</th><th>REVISION</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead><tbody>{release.items.map(item => <tr key={item.id}><td>{item.title} <code>{item.slug}</code></td><td>{item.action}</td><td>{item.revision}</td><td>{allowPublish && (release.status === 'draft' || release.status === 'scheduled') && <button className="text-button muted" disabled={Boolean(busy)} onClick={() => mutate(release, 'removeReleaseEntry', 'mutation($id:ID!,$entryId:ID!,$version:Int!){removeReleaseEntry(id:$id,entryId:$entryId,version:$version)}', { id: release.id, entryId: item.entryId, version: release.version })}>Remove</button>}</td></tr>)}</tbody></table></div> : <p>No entries captured yet.</p>}
      {allowPublish && (release.status === 'draft' || release.status === 'scheduled') && <form className="inline-form" onSubmit={event => add(release, event)}><input name="entryId" required aria-label={`Entry for ${release.name}`} placeholder="Entry id" disabled={Boolean(busy)} /><select name="action" aria-label={`Action for ${release.name}`} defaultValue="publish"><option value="publish">publish</option><option value="unpublish">unpublish</option></select><Button type="submit" variant="outline" disabled={Boolean(busy)}>Add captured revision</Button></form>}
      <div className="inline-form">
        {allowPublish && (release.status === 'draft' || release.status === 'scheduled') && <Button disabled={Boolean(busy)} onClick={() => mutate(release, 'publishRelease', 'mutation($id:ID!,$version:Int!){publishRelease(id:$id,version:$version)}', { id: release.id, version: release.version })}>Publish release</Button>}
        {allowSchedule && (release.status === 'draft' || release.status === 'scheduled') && <form className="inline-form" onSubmit={event => { event.preventDefault(); const when = String(new FormData(event.currentTarget).get('when') || ''); void mutate(release, 'scheduleRelease', 'mutation($id:ID!,$version:Int!,$scheduledAt:String!){scheduleRelease(id:$id,version:$version,scheduledAt:$scheduledAt)}', { id: release.id, version: release.version, scheduledAt: new Date(when).toISOString() }) }}><label>Schedule release<input name="when" type="datetime-local" required aria-label={`Schedule ${release.name}`} /></label><Button type="submit" variant="outline" disabled={Boolean(busy)}>Schedule release</Button></form>}
        {allowPublish && release.status !== 'published' && release.status !== 'cancelled' && <Button variant="outline" disabled={Boolean(busy)} onClick={() => mutate(release, 'cancelRelease', 'mutation($id:ID!,$version:Int!){cancelRelease(id:$id,version:$version)}', { id: release.id, version: release.version })}>Cancel release</Button>}
      </div>
    </article>)}
    {!loading && !releases.length && <p className="empty-state">No releases yet.</p>}
  </>
}
