import { cleanup, render, screen } from '@testing-library/react'
import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, expect, test } from 'vitest'
import { Markdown } from './Markdown'
afterEach(cleanup)
test('formats Markdown while rejecting HTML and unsafe URL schemes',()=>{
  const view=render(<Markdown text={'# Heading\n\n**bold**\n\n- item\n\n```js\nconst value=1\n```\n\n[unsafe](javascript:alert%281%29)\n\n<script>alert(1)</script>\n\n![Cover](asset:image)'} assets={[{id:'image',mime:'image/png',url:'https://media.example/image?expires=123'}]} />)
  expect(screen.getByRole('heading',{name:'Heading'})).toBeTruthy()
  expect(view.container.querySelector('strong')?.textContent).toBe('bold')
  expect(view.container.querySelector('script')).toBeNull()
  expect(view.container.querySelector('a')?.getAttribute('href')).toBe('')
  expect(screen.getByAltText('Cover').getAttribute('src')).toContain('expires=123')
})
test('preserves legacy text line breaks without changing the source',()=>{
  const view=render(<Markdown text={'First line\nSecond line\n\nLast paragraph'} />)
  expect(view.container.querySelector('br')).toBeTruthy()
  expect(view.container.querySelectorAll('p')).toHaveLength(2)
})
test('renders supported Markdown to static HTML',async()=>{
  const {renderToStaticMarkup}=await import('react-dom/server')
  const text='# Same heading\n\n**bold** and [link](https://example.com)\n\n```\ncode\n```\n\n<script>bad()</script>'
  const html=renderToStaticMarkup(<Markdown text={text} />)
  expect(html).toContain('<h1>Same heading</h1>')
  expect(html).toContain('<strong>bold</strong>')
  expect(html).toContain('<a href="https://example.com">link</a>')
  expect(html).toContain('<pre tabindex="0"><code>code\n</code></pre>')
  expect(html).not.toContain('<script>')
})

const hebrewWithNiqqud = 'שָׁלוֹם עוֹלָם'
const bereshit = 'בְּרֵאשִׁית'

function scheme(value: string) {
  try { return new URL(value, window.location.href).protocol } catch { return '' }
}

test('raw HTML and script stay inert and javascript or data URLs stay off href and src', () => {
  const previewWindow = window as Window & { __mossPreviewRan?: number }
  previewWindow.__mossPreviewRan = 0
  const calls: string[] = []
  const originalAlert = window.alert
  window.alert = ((message?: unknown) => { calls.push(String(message)) }) as typeof window.alert
  const text = [
    '# Preview',
    '',
    '```',
    '<script>alert(1)</script>',
    'javascript:alert(1)',
    '```',
    '',
    '<script>window.__mossPreviewRan=1</script>',
    '<img src="https://blocked.example/raw-html.png" onerror="window.__mossPreviewRan=1">',
    '<iframe src="javascript:alert(1)"></iframe>',
    '<a href="javascript:alert(1)">html-js</a>',
    '<a href="data:text/html,hello">html-data</a>',
    '',
    '[js](javascript:alert(1))',
    '[js-upper](JAVASCRIPT:alert(1))',
    '[js-angle](<javascript:alert(1)>)',
    '[data](data:text/html,hello)',
    '[data-upper](DATA:text/html,hello)',
    '[data-image](data:image/png;base64,aaaa)',
    '![js-img](javascript:alert(1))',
    '![data-img](data:text/html,hello)',
    '![svg](data:image/svg+xml;base64,PHN2Zy8+)',
    '[mail](mailto:editor@example.com)',
    '[safe](https://example.com/docs)',
    '![safe-img](https://example.com/cover.png)',
    '![ok](asset:ok)',
    '![bad-asset](asset:bad)',
    '![js-asset](asset:js)',
    '[ref][evil]',
    '',
    '[evil]: javascript:alert(1)',
    '',
    '<javascript:alert(1)>',
    '<data:text/html,hi>',
  ].join('\n')
  const assets = [
    { id: 'ok', mime: 'image/png', url: 'https://media.example/ok.png?expires=9' },
    { id: 'bad', mime: 'image/png', url: 'data:image/png;base64,aaaa' },
    { id: 'js', mime: 'image/png', url: 'javascript:alert(1)' },
  ]
  try {
    const view = render(<Markdown text={text} assets={assets} />)
    const html = renderToStaticMarkup(<Markdown text={text} assets={assets} />)
    expect(previewWindow.__mossPreviewRan).toBe(0)
    expect(calls).toEqual([])
    expect(view.container.querySelector('script, iframe, object, embed, link, meta, style')).toBeNull()
    expect(view.container.querySelector('img[src="https://blocked.example/raw-html.png"]')).toBeNull()
    expect(screen.getByRole('heading', { name: 'Preview' })).toBeTruthy()
    expect(view.container.querySelector('code')?.textContent).toContain('<script>alert(1)</script>')
    expect(view.container.querySelector('code')?.textContent).toContain('javascript:alert(1)')
    for (const element of view.container.querySelectorAll('*')) {
      for (const name of element.getAttributeNames()) expect(name.toLowerCase().startsWith('on')).toBe(false)
    }
    for (const anchor of view.container.querySelectorAll('a')) {
      const href = anchor.getAttribute('href') ?? ''
      expect(href.trim().toLowerCase().startsWith('javascript:')).toBe(false)
      expect(href.trim().toLowerCase().startsWith('data:')).toBe(false)
      expect(scheme(href) === 'javascript:' || scheme(href) === 'data:').toBe(false)
    }
    for (const image of view.container.querySelectorAll('img')) {
      const src = image.getAttribute('src') ?? ''
      expect(src.trim().toLowerCase().startsWith('javascript:')).toBe(false)
      expect(src.trim().toLowerCase().startsWith('data:')).toBe(false)
      expect(scheme(src) === 'javascript:' || scheme(src) === 'data:').toBe(false)
    }
    expect(view.container.querySelector('a[href="https://example.com/docs"]')).toBeTruthy()
    expect(view.container.querySelector('a[href="mailto:editor@example.com"]')).toBeTruthy()
    expect(view.container.querySelector('img[src="https://example.com/cover.png"]')).toBeTruthy()
    expect(view.container.querySelector('img[src="https://media.example/ok.png?expires=9"]')).toBeTruthy()
    expect(html).not.toMatch(/<script[\s>]/i)
    expect(html).not.toMatch(/\s(?:href|src)\s*=\s*["']\s*(?:javascript|data):/i)
    expect(html).not.toMatch(/\son[a-z]+\s*=/i)
    expect(html).toContain('href="https://example.com/docs"')
    expect(html).toContain('href="mailto:editor@example.com"')
    expect(html).toContain('src="https://example.com/cover.png"')
    expect(html).toContain('src="https://media.example/ok.png?expires=9"')
    expect(html).toContain('&lt;script&gt;alert(1)&lt;/script&gt;')
  } finally {
    window.alert = originalAlert
    delete previewWindow.__mossPreviewRan
  }
})

test('renders a Hebrew Markdown fixture with niqqud as text', () => {
  const text = `# ${hebrewWithNiqqud}\n\n${bereshit}\n\n**${hebrewWithNiqqud}**\n\n[${hebrewWithNiqqud}](https://example.com/he)`
  const view = render(<Markdown text={text} />)
  const html = renderToStaticMarkup(<Markdown text={text} />)
  expect(screen.getByRole('heading', { name: hebrewWithNiqqud }).textContent).toBe(hebrewWithNiqqud)
  expect(view.container.textContent).toContain(bereshit)
  expect(view.container.querySelector('strong')?.textContent).toBe(hebrewWithNiqqud)
  expect(view.container.querySelector('a')?.textContent).toBe(hebrewWithNiqqud)
  expect(view.container.querySelector('a')?.getAttribute('href')).toBe('https://example.com/he')
  expect(view.container.textContent).toMatch(/[\u0591-\u05C7]/)
  expect(html).toContain(hebrewWithNiqqud)
  expect(html).toContain(bereshit)
  expect(html).toContain('href="https://example.com/he"')
})
