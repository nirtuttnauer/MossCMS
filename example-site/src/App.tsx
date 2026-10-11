import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react'
import { ArrowDown, ArrowUpRight, BookOpen, ChevronDown, Circle, Folder, Home, RefreshCw, UserRound } from 'lucide-react'
import { ContentImage, type ImageField, type ImageAsset } from './components/ContentImage'
import { Markdown } from './components/Markdown'
import type { MarkdownAsset } from '../../shared/markdown.mjs'
import { pagePath, routeSlug, routePage } from '../../shared/routes.mjs'
import defaults from './content-defaults.json'
import Showcase, { type Slide } from './components/Showcase'

type Link = { label: string; url: string }
type Item = { title: string; description?: string; url?: string; label?: string }
export type Profile = {
  name: string; headline: string; intro?: string; heroName?: string; location?: string
  email?: string; availability?: string; links?: Link[]
  labels?: Partial<typeof defaults.labels>; appearance?: Partial<typeof defaults.appearance>
  resolvedAssets?: MarkdownAsset[]; carouselSeconds?: number; carouselAutoplay?: boolean
}
export type Page = {
  id: string; slug: string; title: string; description?: string; body?: string; order?: number
  kind?: 'home' | 'page' | 'projects' | 'blog' | 'about' | 'contact'
  cover?:ImageField; gallery?:ImageField[]; resolvedAssets?: ImageAsset[]; parentSlug?: string; items?: Item[]; url?: string; linkLabel?: string; aliases?: string[]
}
type Website = { stale?:boolean; preview?: {entryId:string;revision:number;expiresAt:string}; siteUrl: string; profile: Profile | null; pages: Page[]; slides?: Slide[] }
const icons = { home: Home, projects: Folder, blog: BookOpen, about: UserRound, contact: UserRound }
const pageHref = pagePath
const isProjectsPage = (page: Page) => page.kind === 'projects' || page.slug === 'projects'

function safeUrl(raw?: string): string | undefined {
  if (!raw) return undefined
  try {
    const url = new URL(raw)
    return ['https:', 'http:', 'mailto:'].includes(url.protocol) ? url.href : undefined
  } catch { return undefined }
}
function Paragraphs({ text, assets }: { text?: string; assets?: MarkdownAsset[] }) {
  return <Markdown text={text || ''} assets={assets} />
}
function cmsSettings<T extends Record<string, string>>(fallback: T, values?: Partial<T>): T {
  return Object.fromEntries(Object.entries(fallback).map(([key, value]) => [key, typeof values?.[key] === 'string' ? values[key] : value])) as T
}
function themeStyles(appearance: typeof defaults.appearance): CSSProperties {
  return Object.fromEntries(Object.entries(appearance).map(([key, value]) => [
    `--${key.replace(/[A-Z]/g, letter => '-' + letter.toLowerCase())}`,
    /^#[\da-f]{6}$/i.test(value) ? value : defaults.appearance[key as keyof typeof defaults.appearance],
  ])) as CSSProperties
}

export default function App() {
  const [website, setWebsite] = useState<Website | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [previewExpired,setPreviewExpired]=useState(false)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [slug, setSlug] = useState(() => routeSlug(location.pathname) || '')
  const loadSequence=useRef(0)
  const load = useCallback(async (signal?: AbortSignal) => {
    const sequence=++loadSequence.current
    try {
      const response = await fetch('/api/site', { signal })
      if(sequence!==loadSequence.current)return
      if (response.status === 401) {setWebsite(null);setPreviewExpired(true)}
      if (!response.ok) throw new Error('Content unavailable')
      const next=await response.json();if(sequence!==loadSequence.current)return;setWebsite(next); setError(false)
    } catch (reason) {
      if (sequence===loadSequence.current && !(reason instanceof DOMException && reason.name === 'AbortError')) setError(true)
    } finally { if (!signal?.aborted) setLoading(false) }
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    void load(controller.signal)
    const refresh = () => { if (document.visibilityState === 'visible') void load(controller.signal) }
    const events=new EventSource('/api/events');events.onmessage=refresh
    const timer = setInterval(refresh, 10000)
    document.addEventListener('visibilitychange', refresh)
    return () => { events.close(); controller.abort(); clearInterval(timer); document.removeEventListener('visibilitychange', refresh) }
  }, [load])
  useEffect(() => {
    const change = () => setSlug(routeSlug(location.pathname) || '')
    window.addEventListener('popstate', change)
    return () => window.removeEventListener('popstate', change)
  }, [])
  useEffect(()=>{
    if(!website)return
    const legacy=()=>{if(!location.hash || location.hash==='#main-content')return;const page=routePage(website.pages,'/'+location.hash.slice(1));if(page){history.replaceState(null,'',pagePath(page));setSlug(page.slug)}}
    legacy();window.addEventListener('hashchange',legacy);return()=>window.removeEventListener('hashchange',legacy)
  },[website])
  const siteUrl = website?.siteUrl ?? 'http://localhost:5174'
  const domain = new URL(siteUrl).hostname
  const profile = website?.profile
  const labels = cmsSettings(defaults.labels, profile?.labels)
  const appearance = cmsSettings(defaults.appearance, profile?.appearance)
  const pages = [...(website?.pages ?? [])].sort((a, b) => (a.order ?? 100) - (b.order ?? 100) || a.slug.localeCompare(b.slug))
  const navigation = pages.filter(item => !item.parentSlug)
  const home = navigation.find(item => item.kind === 'home' || item.slug === 'home')
  const page = pages.find(item => item.slug === slug) ?? pages.find(item => item.aliases?.includes(slug)) ?? (slug === 'home' ? home : undefined)
  const parent = pages.find(item => item.slug === page?.parentSlug)
  const children = pages.filter(item => item.parentSlug === page?.slug)
  const isHome = page?.kind === 'home'
  const homeHref = home ? pageHref(home) : '/'
  const externalUrl = safeUrl(page?.url)
  const section = parent ?? page
  useEffect(() => {
    if (page && (isProjectsPage(page) || page.parentSlug)) {
      const group = page.parentSlug || page.slug
      setExpanded(previous => new Set(previous).add(group))
    }
  }, [page?.id, page?.parentSlug, page?.slug])
  useEffect(() => {
    document.title = page?.kind === 'home' ? `${profile?.name ?? 'Example website'} — ${domain}` : `${page?.title ?? labels.home} — ${domain}`
    document.querySelector('link[rel="canonical"]')?.setAttribute('href', siteUrl + (page ? pagePath(page) : '/'))
    document.querySelector('meta[property="og:url"]')?.setAttribute('content', siteUrl + (page ? pagePath(page) : '/'))
    document.querySelector('meta[property="og:site_name"]')?.setAttribute('content', labels.brand)
    document.querySelector('meta[property="og:title"]')?.setAttribute('content', document.title)
    const description = page?.description || profile?.headline || 'A example website.'
    document.querySelector('meta[property="og:description"]')?.setAttribute('content', description)
    document.querySelector('meta[name="description"]')?.setAttribute('content', description)
  }, [page?.title, page?.description, page?.kind, page?.slug, profile?.name, profile?.headline, siteUrl, domain, labels.brand, labels.home])
  const toggle = (id: string) => setExpanded(previous => {
    const next = new Set(previous)
    if (next.has(id)) next.delete(id); else next.add(id)
    return next
  })

  async function exitPreview() {await fetch('/api/preview/exit',{method:'POST'});location.replace('/')}
  return <>{website?.stale && <p role="status">Showing recently loaded content while the connection recovers.</p>}<div aria-live="polite">{(website?.preview || previewExpired) && <div className="preview-banner"><strong>{previewExpired ? 'Preview expired or revoked' : `Preview · saved revision ${website!.preview!.revision}`}</strong><span>Draft content · visible until {website?.preview ? new Date(website.preview.expiresAt).toLocaleTimeString() : 'session expiry'}</span><button onClick={()=>void exitPreview()}>Exit preview</button></div>}</div><div className="site-shell" style={themeStyles(appearance)}>
    <a className="skip-link" href="#main-content" onClick={event => { event.preventDefault(); document.getElementById('main-content')?.focus() }}>{labels.skipToContent}</a>
    <aside className="sidebar">
      <a className="identity" href={homeHref} aria-label={labels.home}>
        <span className="monogram">{labels.brand || domain}</span>
      </a>
      <nav aria-label={labels.navigationHeading || 'Main navigation'}>
        {navigation.map((item, index) => {
          const Icon = icons[(item.kind ?? item.slug) as keyof typeof icons] ?? icons[item.slug as keyof typeof icons] ?? Circle
          const projects = isProjectsPage(item)
          const projectPages = pages.filter(child => child.parentSlug === item.slug)
          const open = expanded.has(item.slug)
          const active = page?.id === item.id || parent?.id === item.id
          return <div className="nav-group" key={item.id}>
            <div className={`nav-row ${active ? 'active' : ''}`}>
              <a className="nav-link" href={pageHref(item)} aria-current={page?.id === item.id ? 'page' : undefined}>
                <Icon size={17} strokeWidth={1.6} /><span>{item.title}</span>
                {!projects && <span className="nav-number">{String(index + 1).padStart(2, '0')}</span>}
              </a>
              {projects && <button className={`project-toggle ${open ? 'open' : ''}`} onClick={() => toggle(item.slug)} aria-expanded={open} aria-controls={`project-list-${item.id}`} aria-label={`${labels.toggleProjects}: ${item.title}`}><ChevronDown size={15} /></button>}
            </div>
            {projects && <div className="project-navigation" id={`project-list-${item.id}`} hidden={!open}>
              {projectPages.length ? projectPages.map(project => <a className={`project-nav-link ${page?.id === project.id ? 'active' : ''}`} href={pageHref(project)} key={project.id} aria-current={page?.id === project.id ? 'page' : undefined}><span className="project-dot" /><span>{project.title}</span></a>) : <p className="project-empty">{labels.emptyProjects}</p>}
            </div>}
          </div>
        })}
      </nav>
      <div className="sidebar-foot">
        {profile?.availability && <span className="availability"><i />{profile.availability}</span>}
        {profile?.location && <span className="location">{profile.location}</span>}
        <div className="social-links">{profile?.links?.map(link => {
          const url = safeUrl(link.url)
          return url && <a key={link.label} href={url} target={url.startsWith('http') ? '_blank' : undefined} rel="noreferrer">{link.label}<ArrowUpRight size={13} /></a>
        })}</div>
        <span className="copyright">© {new Date().getFullYear()} {profile?.name}</span>
      </div>
    </aside>
    <main className="main-view" id="main-content" tabIndex={-1} aria-busy={loading}>
      {!isHome && <header className="view-header"><span>{section?.title?.toUpperCase() ?? labels.headerTitle}</span><span className="header-mark"><span />{labels.headerTagline}</span></header>}
      {error && <div className="error-message" role="alert"><span>{labels.loadError}</span><button onClick={() => void load()}><RefreshCw size={14} />{labels.retry}</button></div>}
      {loading ? <div className="loading-view" role="status"><div className="loading-line" /><div className="loading-line short" /><p>{labels.loading}</p></div> : !profile ? <section className="empty-view"><span className="eyebrow">{labels.welcomeEyebrow}</span><h1>{labels.emptySiteTitle}</h1><p>{labels.emptySiteBody}</p></section> : !page ? <section className="empty-view"><span className="eyebrow">404</span><h1>{labels.notFoundTitle}</h1><p>{labels.notFoundBody}</p><a className="text-link" href={homeHref}>{labels.home} <ArrowUpRight size={15} /></a></section> : isHome && website?.slides?.some(slide => slide.enabled !== false) ? <Showcase slides={website.slides} pages={pages} profile={profile} labels={labels} /> : <article key={page.id} className="page-content">
        <div className="eyebrow"><span className="small-rule" />{isHome ? labels.welcomeEyebrow : parent ? <a href={pageHref(parent)}>{parent.title} / {page.title}</a> : `${String(navigation.findIndex(item => item.id === page.id) + 1).padStart(2, '0')} / ${page.title}`}</div>
        {isHome ? <>
          <h1>{labels.greeting}<br />{labels.namePrefix} <em>{profile.heroName || profile.name}.</em></h1>
          <p className="headline">{profile.headline}</p>
          <div className="intro-copy"><Paragraphs text={profile.intro || page.body} assets={profile.intro ? profile.resolvedAssets : page.resolvedAssets} /></div>
          <a className="discover-link" href={pageHref(navigation.find(isProjectsPage) ?? navigation.find(item => item.id !== page.id) ?? page)}><span>{labels.discover}</span><ArrowDown size={16} /></a>
          <div className="section-divider"><span>{labels.sectionHeading}</span><span>01 — {String(navigation.length).padStart(2, '0')}</span></div>
          <div className="page-grid">{navigation.filter(item => item.id !== page.id).map((item, index) => <a className="page-card" href={pageHref(item)} key={item.id}><div className="card-top"><span>{String(index + 2).padStart(2, '0')}</span><ArrowUpRight size={21} strokeWidth={1.5} /></div><h2>{item.title}</h2><p>{item.description}</p></a>)}</div>
        </> : <>
          <h1>{page.title}<em>.</em></h1>
          {page.description && <p className="headline">{page.description}</p>}
          <ContentImage image={page.cover} assets={page.resolvedAssets} priority /><div className="article-copy"><Paragraphs text={page.body} assets={page.resolvedAssets} /></div>
          {!!page.gallery?.length && <div className="project-gallery">{page.gallery.map((image,index)=><ContentImage key={`${image.asset}-${index}`} image={image} assets={page.resolvedAssets} />)}</div>}
          {externalUrl && <a className="text-link" href={externalUrl} target={externalUrl.startsWith('http') ? '_blank' : undefined} rel="noreferrer">{page.linkLabel || labels.visitLink}<ArrowUpRight size={16} /></a>}
          {['contact', 'about'].includes(page.kind ?? '') && profile.email && <a className="contact-link" href={`mailto:${encodeURIComponent(profile.email)}`}>{profile.email}<ArrowUpRight size={24} /></a>}
          {children.length > 0 && <div className="child-pages">{children.map((child, index) => <a className="child-page" href={pageHref(child)} key={child.id}><span className="item-number">{String(index + 1).padStart(2, '0')}</span><div><ContentImage image={child.cover} assets={child.resolvedAssets} /><h2>{child.title}</h2><p>{child.description}</p></div><ArrowUpRight size={21} /></a>)}</div>}
          {page.items?.length ? <div className="item-list">{page.items.map((item, index) => {
            const url = safeUrl(item.url)
            return <section className="content-item" key={index}><span className="item-number">{String(index + 1).padStart(2, '0')}</span><div><h2>{item.title}</h2><Paragraphs text={item.description} assets={page.resolvedAssets} />{url && <a className="text-link" href={url} target={url.startsWith('http') ? '_blank' : undefined} rel="noreferrer">{item.label || labels.visitLink}<ArrowUpRight size={16} /></a>}</div></section>
          })}</div> : !children.length && !page.body && !externalUrl && <div className="quiet-note">{isProjectsPage(page) ? labels.emptyProjects : labels.emptyPage}</div>}
        </>}
        <footer className="page-footer"><span>{profile.name}</span><a href={homeHref}>{labels.backHome} <ArrowUpRight size={12} /></a></footer>
      </article>}
    </main>
  </div></>
}
