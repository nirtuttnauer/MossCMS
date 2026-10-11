import {pagePath} from '../../../shared/routes.mjs'
import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { ArrowLeft, ArrowRight, ArrowUpRight, Pause, Play } from 'lucide-react'
import defaults from '../content-defaults.json'
import type { Page, Profile } from '../App'
import LiquidScene from './LiquidScene'
import ThreeScene from './ThreeScene'

export type Slide = {
  id: string; slug: string; title: string; kind: 'liquid' | 'three' | 'promotion' | 'blog'
  eyebrow?: string; description?: string; linkUrl?: string; linkLabel?: string
  primaryColor?: string; secondaryColor?: string; backgroundColor?: string; textColor?: string
  duration?: number; speed?: number; enabled?: boolean
}
type Props = { slides: Slide[]; pages: Page[]; profile: Profile; labels: typeof defaults.labels }
const color = (raw: string | undefined, fallback: string) => raw && /^#[\da-f]{6}$/i.test(raw) ? raw : fallback
const bounded = (value: number | undefined, fallback: number, min: number, max: number) => Number.isFinite(value) ? Math.min(max, Math.max(min, value!)) : fallback
function href(raw?: string) {
  if (!raw) return undefined
  if (raw.startsWith('#')) return raw
  try { const url = new URL(raw); return ['http:', 'https:', 'mailto:'].includes(url.protocol) ? url.href : undefined } catch { return undefined }
}
function shuffle<T>(items: T[], previousId?: string): T[] {
  const result = [...items]
  for (let i = result.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[result[i], result[j]] = [result[j], result[i]]
  }
  if (result.length > 1 && (result[0] as Slide).id === previousId) [result[0], result[1]] = [result[1], result[0]]
  return result
}

export default function Showcase({ slides, pages, profile, labels }: Props) {
  const blogSlugs = pages.filter(page => page.kind === 'blog' || page.slug === 'blog').map(page => page.slug)
  // Blog templates produce a slide for each published post, with its real title and URL.
  const eligible = slides.filter(slide => slide.enabled !== false).flatMap(slide => slide.kind === 'blog'
    ? pages.filter(page => page.parentSlug && blogSlugs.includes(page.parentSlug)).map(post => ({
      ...slide, id: `${slide.id}:${post.id}`, title: post.title, description: post.description || post.body?.slice(0, 240),
      linkUrl: pagePath(post), linkLabel: slide.linkLabel || labels.readBlog,
    })) : [slide])
  const signature = JSON.stringify(eligible)
  // Keep the shuffled deck stable during the CMS's periodic content refresh.
  const deck = useMemo(() => shuffle(eligible), [signature])
  const [order, setOrder] = useState(deck)
  const [position, setPosition] = useState(0)
  const [paused, setPaused] = useState(profile.carouselAutoplay === false)
  const [hovered, setHovered] = useState(false)
  const [focused, setFocused] = useState(false)
  const [visible, setVisible] = useState(document.visibilityState === 'visible')
  const [inView, setInView] = useState(true)
  const [reduced, setReduced] = useState(() => matchMedia('(prefers-reduced-motion: reduce)').matches)
  const [progress, setProgress] = useState(0)
  const stage = useRef<HTMLElement>(null)
  const slide = order[position] ?? order[0]
  const animationsRunning = !paused && visible && inView && !reduced
  const running = animationsRunning && !hovered && !focused
  const duration = bounded(slide?.duration ?? profile.carouselSeconds, 12, 5, 120) * 1000
  useEffect(() => { setOrder(deck); setPosition(0); setProgress(0) }, [deck])
  useEffect(() => { setPaused(profile.carouselAutoplay === false) }, [profile.carouselAutoplay])
  useEffect(() => {
    const media = matchMedia('(prefers-reduced-motion: reduce)')
    const change = () => setReduced(media.matches)
    const visibility = () => setVisible(document.visibilityState === 'visible')
    media.addEventListener('change', change); document.addEventListener('visibilitychange', visibility)
    const observer = new IntersectionObserver(([entry]) => setInView(entry.isIntersecting))
    if (stage.current) observer.observe(stage.current)
    return () => { media.removeEventListener('change', change); document.removeEventListener('visibilitychange', visibility); observer.disconnect() }
  }, [])
  const advance = (direction: number) => {
    setProgress(0)
    if (direction > 0 && position >= order.length - 1) {
      setOrder(previous => shuffle(previous, previous[position]?.id)); setPosition(0)
    } else setPosition(previous => (previous + direction + order.length) % order.length)
  }
  useEffect(() => {
    if (!running || order.length < 2) return
    const start = performance.now()
    const initial = progress
    const timer = setInterval(() => {
      const next = initial + (performance.now() - start) / duration
      if (next >= 1) { clearInterval(timer); advance(1) } else setProgress(next)
    }, 100)
    return () => clearInterval(timer)
    // Progress is sampled when playback resumes, without restarting the timer on every tick.
  }, [running, position, slide?.id, duration, order])
  if (!slide) return <section className="empty-view"><h1>{profile.name}</h1><p>{profile.headline}</p></section>
  const primary = color(slide.primaryColor, '#93E2C1')
  const secondary = color(slide.secondaryColor, '#819AEF')
  const background = color(slide.backgroundColor, '#142029')
  const text = color(slide.textColor, '#F2F4F6')
  const speed = bounded(slide.speed, 1, 0.2, 3)
  const url = href(slide.linkUrl)
  const style = { '--slide-primary': primary, '--slide-secondary': secondary, '--slide-background': background, '--slide-text': text } as CSSProperties
  return <section ref={stage} className="showcase" style={style} role="region" aria-roledescription="carousel" aria-label={labels.showcase}
    onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}
    onFocusCapture={() => setFocused(true)} onBlurCapture={event => { if (!event.currentTarget.contains(event.relatedTarget)) setFocused(false) }}>
    <div key={slide.id} className={`showcase-slide ${slide.kind}`} role="group" aria-roledescription="slide" aria-label={`${position + 1} / ${order.length}: ${slide.title}`}>
      {slide.kind === 'liquid' ? <LiquidScene primary={primary} secondary={secondary} background={background} speed={speed} running={animationsRunning} />
        : slide.kind === 'three' ? <ThreeScene primary={primary} secondary={secondary} background={background} speed={speed} running={animationsRunning} />
        : <div className="editorial-art" aria-hidden="true"><span className="art-orbit" /><span className="art-orbit second" /><span className="art-dot" /></div>}
      <div className="showcase-top"><span>{labels.headerTitle}</span><span>{labels.headerTagline}</span></div>
      <div className="showcase-copy">
        {slide.eyebrow && <div className="showcase-eyebrow"><span />{slide.eyebrow}</div>}
        <h1>{slide.title}</h1>
        {slide.description && <p>{slide.description}</p>}
        {url && <a className="showcase-link" href={url} target={url.startsWith('http') ? '_blank' : undefined} rel="noreferrer">{slide.linkLabel || labels.visitLink}<ArrowUpRight size={18} /></a>}
      </div>
    </div>
    <div className="showcase-controls">
      <div className="showcase-status"><span className="showcase-counter">{String(position + 1).padStart(2, '0')} <span>/ {String(order.length).padStart(2, '0')}</span></span><span className="showcase-status-label">{labels.showcase}</span></div>
      <div className="showcase-dots">{order.map((item, index) => <button key={item.id} className={index === position ? 'selected' : ''} aria-label={`${labels.goToSlide}: ${item.title}`} aria-current={index === position ? 'true' : undefined} onClick={() => { setPosition(index); setProgress(0) }} />)}</div>
      <div className="showcase-buttons">
        <button aria-label={labels.previousSlide} onClick={() => advance(-1)} disabled={order.length < 2}><ArrowLeft size={18} /></button>
        {!reduced && <button aria-label={paused ? labels.playShowcase : labels.pauseShowcase} aria-pressed={paused} onClick={() => { setPaused(previous => !previous) }}>{paused ? <Play size={15} /> : <Pause size={15} />}</button>}
        <button aria-label={labels.nextSlide} onClick={() => advance(1)} disabled={order.length < 2}><ArrowRight size={18} /></button>
      </div>
    </div>
    <div className="showcase-progress" aria-hidden="true"><span style={{ width: `${progress * 100}%` }} /></div>
  </section>
}
