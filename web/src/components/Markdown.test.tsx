import { cleanup, render, screen } from '@testing-library/react'
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
test('CMS preview and website render the same supported Markdown',async()=>{
  const {Markdown:WebsiteMarkdown}=await import('../../../personal-site/src/components/Markdown')
  const {renderToStaticMarkup}=await import('react-dom/server')
  const text='# Same heading\n\n**bold** and [link](https://example.com)\n\n```\ncode\n```\n\n<script>bad()</script>'
  expect(renderToStaticMarkup(<Markdown text={text} />)).toBe(renderToStaticMarkup(<WebsiteMarkdown text={text} />))
})
