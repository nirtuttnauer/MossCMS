import { useEffect, useState } from 'react'
import { Activity, Blocks, Code2, FileText, FolderOpen, LayoutDashboard, LogOut, Settings2, Users } from 'lucide-react'
import { Button } from '../components/ui/button'
import { gql, message, rest, setContext, typeFields, type ContentType, type Me, type Provider } from '../lib/api'
import { Assets } from './Assets'
import { Auth } from './Auth'
import { Content } from './Content'
import { Explorer } from './Explorer'
import { Settings } from './Settings'
import { Team } from './Team'
import { Types } from './Types'

type Overview = { total: number; published: number; drafts: number; scheduled: number; types: number; assets: number; members: number }
const navigation = [{ key: 'overview', name: 'Overview', icon: LayoutDashboard }, { key: 'content', name: 'Content', icon: FileText }, { key: 'types', name: 'Content types', icon: Blocks }, { key: 'assets', name: 'Assets', icon: FolderOpen }, { key: 'team', name: 'Team', icon: Users }, { key: 'explorer', name: 'API explorer', icon: Code2 }, { key: 'settings', name: 'Settings', icon: Settings2 }]

export default function App() {
  const [me, setMe] = useState<Me | null>(null)
  const [initialized, setInitialized] = useState(true)
  const [providers, setProviders] = useState<Provider[]>([])
  const [booting, setBooting] = useState(true)
  const [projectId, setProjectId] = useState(localStorage.getItem('moss-project') || '')
  const [route, setRoute] = useState(location.hash.slice(1).split('?')[0] || 'content')
  const [types, setTypes] = useState<ContentType[]>([])
  const [overview, setOverview] = useState<Overview | null>(null)
  const [refresh, setRefresh] = useState(0)
  const [error, setError] = useState('')
  const [connected, setConnected] = useState(false)
  const project = me?.projects.find(p => p.id === projectId) || me?.projects[0]
  setContext(project?.id || '', me?.csrf || '')
  async function loadAccount() {
    setError('')
    try {
      const status = await rest<{ initialized: boolean; providers: Provider[] }>('/auth/status')
      setInitialized(status.initialized); setProviders(status.providers)
      try { const account = await rest<Me>('/auth/me'); setMe(account) } catch { setMe(null) }
    } catch (reason) { setError(message(reason)) }
    finally { setBooting(false) }
  }
  useEffect(() => { void loadAccount(); const change = () => setRoute(location.hash.slice(1).split('?')[0] || 'content'); window.addEventListener('hashchange', change); return () => window.removeEventListener('hashchange', change) }, [])
  useEffect(() => { let active = true; const check = () => fetch('/ready').then(response => { if (active) setConnected(response.ok) }).catch(() => { if (active) setConnected(false) }); void check(); const timer = setInterval(check, 30000); return () => { active = false; clearInterval(timer) } }, [])
  useEffect(() => {
    if (!me || !project) return
    let alive = true
    setContext(project.id, me.csrf); setError('')
    gql<{ contentTypes: ContentType[]; overview: Overview }>(`{contentTypes{${typeFields}} overview}`).then(result => { if (alive) { setTypes(result.contentTypes); setOverview(result.overview) } }).catch(reason => { if (alive) setError(message(reason)) })
    return () => { alive = false }
  }, [project?.id, me?.csrf, refresh])
  const changed = () => setRefresh(v => v + 1)
  async function logout() { try { await rest('/auth/logout', 'POST'); setMe(null); location.hash = 'login' } catch (reason) { setError(message(reason)) } }
  if (booting) return <div className="auth-shell"><p>Connecting to MossCMS…</p></div>
  if (!me || !initialized || (!me.authSkipped && (route.startsWith('invite/') || route.startsWith('reset/')))) return <>{error && <p className="form-error">{error}</p>}<Auth initialized={initialized} providers={providers} me={me} onSuccess={loadAccount} /></>
  if (!project) return <div className="auth-shell"><section className="auth-card"><h1>No workspace access</h1><p>Ask an administrator for an invitation or create a workspace.</p><form className="editor-form" onSubmit={async event => { event.preventDefault(); try { await rest('/api/projects', 'POST', Object.fromEntries(new FormData(event.currentTarget))); await loadAccount() } catch (reason) { setError(message(reason)) } }}><label>Name<input name="name" required /></label><Button type="submit">Create workspace</Button></form>{error && <p className="form-error">{error}</p>}<Button variant="outline" onClick={logout}>Sign out</Button></section></div>
  const initials = me.user.name.split(' ').map(s => s[0]).slice(0, 2).join('').toUpperCase()
  const active = navigation.find(n => n.key === route)?.name || 'Content'
  return <div className="shell"><aside className="sidebar"><a className="brand" href="#overview" aria-label="MossCMS overview"><div className="brand-mark"><span /></div><span>Moss<span className="brand-light">CMS</span></span></a><div className="project-switch"><div className="project-avatar">{project.name[0].toUpperCase()}</div><div className="project-copy"><select aria-label="Workspace" value={project.id} onChange={event => { setProjectId(event.target.value); localStorage.setItem('moss-project', event.target.value); setTypes([]); setOverview(null) }}>{me.projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select><span>{project.role}</span></div></div><nav className="sidebar-nav" aria-label="Main navigation"><div className="nav-group"><p>Workspace</p>{navigation.map(item => <a key={item.key} title={item.name} aria-label={item.name} aria-current={route === item.key ? 'page' : undefined} href={`#${item.key}`} className={`nav-item ${route === item.key ? 'selected' : ''}`}><item.icon size={17} strokeWidth={1.8} /><span>{item.name}</span>{item.key === 'content' && <span className="nav-count">{overview?.total ?? '—'}</span>}</a>)}</div></nav><div className="sidebar-bottom">{!me.authSkipped && <button className="nav-item" title="Sign out" aria-label="Sign out" onClick={logout}><LogOut size={17} /><span>Sign out</span></button>}<div className="user-card"><div className="user-avatar">{initials}</div><div className="user-copy"><strong>{me.user.name}</strong><span>{project.role}</span></div></div></div></aside><main className="main"><header className="topbar"><div className="breadcrumbs"><span>{project.name}</span><span className="slash">/</span><strong>{active}</strong></div><div className="top-actions">{me.authSkipped && <span className="dev-auth-status">Local development</span>}<span className={`api-status ${!connected ? 'offline' : ''}`}><span />{connected ? 'API operational' : 'API unavailable'}</span><div className="top-avatar">{initials}</div></div></header><div className="content-wrap">{error && <div className="notice error-state" role="alert">{error} <Button variant="outline" onClick={() => { changed(); void loadAccount() }}>Retry</Button></div>}<div key={project.id}>{route === 'overview' ? <><div className="page-heading"><div><div className="eyebrow">WORKSPACE AT A GLANCE</div><h1>Overview</h1><p className="subtitle">Live content and team activity in {project.name}.</p></div></div><section className="stats">{(['total', 'published', 'drafts', 'scheduled', 'types', 'assets', 'members'] as const).map(key => <div className="stat-card" key={key}><div className="stat-top"><span>{key}</span><Activity size={16} /></div><strong>{overview?.[key] ?? '—'}</strong></div>)}</section><section className="plain-card"><h2>Build with your data</h2><p>Define a content type, write and publish entries, then create a delivery token for each frontend.</p><div className="inline-form"><a className="button button-outline" href="#types">Define types</a><a className="button button-outline" href="#content">Manage content</a><a className="button button-outline" href="#settings">Frontend access</a></div></section></> : route === 'types' ? <Types types={types} role={project.role} onChanged={changed} /> : route === 'assets' ? <Assets role={project.role} onChanged={changed} /> : route === 'team' ? <Team role={project.role} onChanged={() => { void loadAccount(); changed() }} /> : route === 'settings' ? <Settings project={project} me={me} providers={providers} types={types} onChanged={() => { void loadAccount(); changed() }} /> : route === 'explorer' ? <Explorer types={types} /> : <Content types={types} role={project.role} onChanged={changed} />}</div><div className="bottom-note"><span>One source of truth. Every frontend.</span><a href="#explorer">Explore the GraphQL API →</a></div></div></main></div>
}
