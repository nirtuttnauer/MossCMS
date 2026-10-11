import { useEffect, useRef, useState } from 'react'
import { confirmNavigation } from '../lib/unsaved'
import { ArrowUpRight, Blocks, CalendarClock, Code2, FileText, FolderOpen, LayoutDashboard, LogOut, Menu, SearchCheck, Settings2, Users } from 'lucide-react'
import { Button } from '../components/ui/button'
import { gql, message, rest, setContext, typeFields, type ContentType, type Me, type Provider } from '../lib/api'
import { Assets } from './Assets'
import { Auth } from './Auth'
import { PublicationQueue } from './PublicationQueue'
import { Content } from './Content'
import { SeoAudit } from './SeoAudit'
import { Explorer } from './Explorer'
import { Settings } from './Settings'
import { Team } from './Team'
import { Types } from './Types'
import { OnboardingChecklist } from '../components/OnboardingChecklist'

type Overview = { total: number; published: number; drafts: number; scheduled: number; types: number; assets: number; members: number }
const navigation = [{ key: 'overview', name: 'Overview', icon: LayoutDashboard }, { key: 'content', name: 'Content', icon: FileText }, { key: 'publications', name: 'Publications', icon: CalendarClock }, { key: 'seo', name: 'SEO audit', icon: SearchCheck }, { key: 'types', name: 'Content types', icon: Blocks }, { key: 'assets', name: 'Assets', icon: FolderOpen }, { key: 'team', name: 'Team', icon: Users }, { key: 'explorer', name: 'API explorer', icon: Code2 }, { key: 'settings', name: 'Settings', icon: Settings2 }]
const metrics = [
  { key: 'total', label: 'Total entries', hint: 'Your content library', route: 'content', icon: FileText },
  { key: 'published', label: 'Published', hint: 'Available to your frontends', route: 'content', icon: ArrowUpRight },
  { key: 'drafts', label: 'Drafts', hint: 'Unpublished entries', route: 'content', icon: FileText },
  { key: 'scheduled', label: 'Scheduled', hint: 'Planned publications', route: 'publications', icon: CalendarClock },
  { key: 'types', label: 'Content types', hint: 'Structure your content', route: 'types', icon: Blocks },
  { key: 'assets', label: 'Assets', hint: 'Images and documents', route: 'assets', icon: FolderOpen },
  { key: 'members', label: 'Team members', hint: 'Workspace collaborators', route: 'team', icon: Users },
] as const

export default function App() {
  const [me, setMe] = useState<Me | null>(null)
  const [initialized, setInitialized] = useState(true)
  const [providers, setProviders] = useState<Provider[]>([])
  const [booting, setBooting] = useState(true)
  const [projectId, setProjectId] = useState(() => {
    const p = new URLSearchParams(location.hash.split('?')[1] || '')
    return p.get('workspace') || localStorage.getItem('moss-project') || ''
  })
  const lastHashRef = useRef(location.hash)
  const [hash, setHash] = useState(location.hash.slice(1) || 'content')
  const route = hash.split('?')[0]
  const [workspaceData, setWorkspaceData] = useState<{ projectId: string; types: ContentType[]; overview: Overview | null }>({ projectId: '', types: [], overview: null })
  const [refresh, setRefresh] = useState(0)
  const [error, setError] = useState('')
  const [connected, setConnected] = useState(false)
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const project = me?.projects.find(p => p.id === projectId) || me?.projects[0]
  const workspaceReady = workspaceData.projectId === project?.id
  const types = workspaceReady ? workspaceData.types : []
  const overview = workspaceReady ? workspaceData.overview : null
  setContext(project?.id || '', me?.csrf || '')
  async function loadAccount() {
    setError('')
    try {
      const status = await rest<{ initialized: boolean; providers: Provider[] }>('/auth/status')
      setInitialized(status.initialized); setProviders(status.providers)
      try {
        const account = await rest<Me>('/auth/me');
        setMe(account);
        const p = new URLSearchParams(location.hash.split('?')[1] || '');
        const wsParam = p.get('workspace');
        if (wsParam && account.projects.some(proj => proj.id === wsParam)) {
          setProjectId(wsParam);
          localStorage.setItem('moss-project', wsParam);
        }
      } catch { setMe(null) }
    } catch (reason) { setError(message(reason)) }
    finally { setBooting(false) }
  }
  useEffect(() => { void loadAccount() }, [])
  useEffect(() => {
    const change = (event: Event) => {
      const currentFullHash = location.hash;
      if (currentFullHash === lastHashRef.current) return;
      if (!confirmNavigation()) {
        event.preventDefault();
        event.stopImmediatePropagation();
        history.replaceState(null, '', lastHashRef.current);
        return;
      }
      lastHashRef.current = currentFullHash;
      const next = location.hash.slice(1) || 'content';
      const query = location.hash.split('?')[1] || '';
      const p = new URLSearchParams(query);
      const ws = p.get('workspace');
      if (ws && me?.projects.some(proj => proj.id === ws) && ws !== projectId) {
        setProjectId(ws);
        localStorage.setItem('moss-project', ws);
      }
      setHash(next);
      event.stopImmediatePropagation();
      window.dispatchEvent(new Event("moss:navigationaccepted"));
    };
    const accepted = () => { lastHashRef.current = location.hash; setHash(location.hash.slice(1) || 'content') };
    window.addEventListener('popstate', change, true);
    window.addEventListener('hashchange', change, true);
    window.addEventListener('moss:locationchange', accepted);
    return () => { window.removeEventListener('popstate', change, true); window.removeEventListener('hashchange', change, true); window.removeEventListener('moss:locationchange', accepted) };
  }, [me?.projects, projectId])
  useEffect(() => { let active = true; const check = () => fetch('/ready').then(response => { if (active) setConnected(response.ok) }).catch(() => { if (active) setConnected(false) }); void check(); const timer = setInterval(check, 30000); return () => { active = false; clearInterval(timer) } }, [])
  useEffect(() => {
    if (!me || !project) return
    let alive = true
    setContext(project.id, me.csrf); setError('')
    gql<{ contentTypes: ContentType[]; overview: Overview }>(`{contentTypes{${typeFields}} overview}`).then(result => { if (alive) setWorkspaceData({ projectId: project.id, types: result.contentTypes, overview: result.overview }) }).catch(reason => { if (alive) setError(message(reason)) })
    return () => { alive = false }
  }, [project?.id, me?.csrf, refresh])
  const changed = () => setRefresh(v => v + 1)
  useEffect(() => { window.scrollTo(0, 0); setMobileNavOpen(false) }, [hash, project?.id])
  async function logout() { if (!confirmNavigation()) return; try { await rest('/auth/logout', 'POST'); setMe(null); location.hash = 'login' } catch (reason) { setError(message(reason)) } }
  if (booting) return <div className="auth-shell"><p>Connecting to MossCMS…</p></div>
  if (!me || !initialized || (!me.authSkipped && (route.startsWith('invite/') || route.startsWith('reset/')))) return <>{error && <p className="form-error">{error}</p>}<Auth initialized={initialized} providers={providers} me={me} onSuccess={loadAccount} /></>
  if (!project) return <div className="auth-shell"><section className="auth-card"><h1>No workspace access</h1><p>Ask an administrator for an invitation or create a workspace.</p><form className="editor-form" onSubmit={async event => { event.preventDefault(); try { await rest('/api/projects', 'POST', Object.fromEntries(new FormData(event.currentTarget))); await loadAccount() } catch (reason) { setError(message(reason)) } }}><label>Name<input name="name" required /></label><Button type="submit">Create workspace</Button></form>{error && <p className="form-error">{error}</p>}<Button variant="outline" onClick={logout}>Sign out</Button></section></div>
  const initials = me.user.name.split(' ').map(s => s[0]).slice(0, 2).join('').toUpperCase()
  const active = navigation.find(n => n.key === route)?.name || 'Content'
  return <div className="shell"><a className="skip-link" href="#main-content" onClick={event => { event.preventDefault(); document.getElementById("main-content")?.focus() }}>Skip to content</a><aside className={`sidebar ${mobileNavOpen ? 'nav-open' : ''}`}><a className="brand" href="#overview" aria-label="MossCMS overview"><div className="brand-mark"><span /></div><span>Moss<span className="brand-light">CMS</span></span></a><div className="project-switch"><div className="project-avatar">{project.name[0].toUpperCase()}</div><div className="project-copy"><select aria-label="Workspace" value={project.id} onChange={event => {
            if (!confirmNavigation()) return;
            const newWs = event.target.value;
            setProjectId(newWs);
            localStorage.setItem('moss-project', newWs);
            setWorkspaceData({ projectId: '', types: [], overview: null });
            const p = new URLSearchParams(location.hash.split('?')[1] || '');
            p.set('workspace', newWs);
            p.delete('entry'); p.delete('field'); p.delete('seoSnapshot');
            const base = location.hash.slice(1).split('?')[0] || 'content';
            const newHash = p.toString() ? `#${base}?${p.toString()}` : `#${base}`;
            lastHashRef.current = newHash;
            history.replaceState(null, '', newHash);
            setHash(newHash.slice(1));
            window.dispatchEvent(new Event("moss:locationchange"));
          }}>{me.projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select><span>{project.role}</span></div></div><button type="button" className="mobile-nav-toggle" aria-expanded={mobileNavOpen} aria-controls="workspace-navigation" onClick={() => setMobileNavOpen(open => !open)}><Menu size={16} aria-hidden="true" />{mobileNavOpen ? 'Hide workspace menu' : 'Workspace menu'}</button><nav className="sidebar-nav" id="workspace-navigation" aria-label="Main navigation"><div className="nav-group"><p>Workspace</p>{navigation.map(item => <a key={item.key} title={item.name} aria-label={item.name} aria-current={route === item.key ? 'page' : undefined} href={`#${item.key}`} className={`nav-item ${route === item.key ? 'selected' : ''}`}><item.icon size={18} strokeWidth={1.8} aria-hidden="true" /><span>{item.name}</span>{item.key === 'content' && <span className="nav-count">{overview?.total ?? '—'}</span>}</a>)}</div></nav><div className="sidebar-bottom">{!me.authSkipped && <button className="nav-item" title="Sign out" aria-label="Sign out" onClick={logout}><LogOut size={17} /><span>Sign out</span></button>}<div className="user-card"><div className="user-avatar">{initials}</div><div className="user-copy"><strong>{me.user.name}</strong><span>{project.role}</span></div></div></div></aside><main className="main" id="main-content" tabIndex={-1}><header className="topbar"><div className="breadcrumbs"><span>{project.name}</span><span className="slash">/</span><strong>{active}</strong>{hash.includes('entry=') && <><span className="slash">/</span><strong>Edit entry</strong></>}</div><div className="top-actions">{me.authSkipped && <span className="dev-auth-status">Local development</span>}<span className={`api-status ${!connected ? 'offline' : ''}`}><span />{connected ? 'API operational' : 'API unavailable'}</span><div className="top-avatar">{initials}</div></div></header><div className="content-wrap">{error && <div className="notice error-state" role="alert">{error} <Button variant="outline" onClick={() => { changed(); void loadAccount() }}>Retry</Button></div>}<div key={project.id}>{workspaceReady ? <>{["overview", "content"].includes(route) && !new URLSearchParams(hash.split("?")[1] || "").has("entry") && <OnboardingChecklist project={project} userId={me.user.id} role={project.role} types={types} overview={overview} onChanged={changed} />}{route === 'overview' ? <><div className="page-heading"><div><div className="eyebrow">WORKSPACE AT A GLANCE</div><h1>Overview</h1><p className="subtitle">Live content and team activity in {project.name}.</p></div></div><section className="stats" aria-label="Workspace metrics">{metrics.map(metric => <a className={`stat-card stat-${metric.key}`} key={metric.key} href={`#${metric.route}`}><div className="stat-top"><span>{metric.label}</span><metric.icon size={18} aria-hidden="true" /></div><strong>{overview?.[metric.key] ?? '—'}</strong><span className="stat-note">{metric.hint}<ArrowUpRight size={14} aria-hidden="true" /></span></a>)}</section><section className="plain-card"><h2>Build with your data</h2><p>Define a content type, write and publish entries, then create a delivery token for each frontend.</p><div className="inline-form"><a className="button button-outline" href="#types">Define types</a><a className="button button-outline" href="#content">Manage content</a><a className="button button-outline" href="#settings">Frontend access</a></div></section></> : route === 'publications' ? <PublicationQueue types={types} role={project.role} onChanged={changed} /> : route === 'seo' ? <SeoAudit types={types} projectId={project.id} /> : route === 'types' ? <Types types={types} role={project.role} onChanged={changed} /> : route === 'assets' ? <Assets role={project.role} onChanged={changed} /> : route === 'team' ? <Team role={project.role} onChanged={() => { void loadAccount(); changed() }} /> : route === 'settings' ? <Settings project={project} me={me} providers={providers} types={types} onChanged={() => { void loadAccount(); changed() }} /> : route === 'explorer' ? <Explorer types={types} /> : <Content types={types} role={project.role} projectId={project.id} defaultLocale={project.defaultLocale} locales={project.locales} onChanged={changed} />}</> : <p role="status">{error ? "Workspace data unavailable. Use Retry above." : "Loading workspace…"}</p>}</div><div className="bottom-note"><span>One source of truth. Every frontend.</span><a href="#explorer">Explore the GraphQL API →</a></div></div></main></div>
}
