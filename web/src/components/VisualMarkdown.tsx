import { useEffect, useRef } from 'react'
import { parseRichText, serializeRichText, type Block, type Inline } from '../../../shared/richtext.mjs'

type Props = {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
}

function domFor(inline: Inline) {
  const element = document.createElement(
    inline.type === 'strong' ? 'strong'
      : inline.type === 'em' ? 'em'
        : inline.type === 'code' ? 'code'
          : inline.type === 'link' ? 'a'
            : inline.type === 'image' ? 'img'
              : 'span',
  )
  if (inline.type === 'link') element.setAttribute('href', inline.href)
  if (inline.type === 'image') {
    element.setAttribute('alt', inline.alt)
    element.setAttribute('data-asset', inline.assetId)
  } else element.textContent = 'text' in inline ? inline.text : ''
  return element
}

function inlinesFrom(node: HTMLElement): Inline[] | null {
  const inlines: Inline[] = []
  for (const child of node.childNodes) {
    if (child.nodeType === Node.TEXT_NODE) {
      if (child.textContent) inlines.push({ type: 'text', text: child.textContent })
      continue
    }
    if (!(child instanceof HTMLElement)) return null
    if (child.tagName === 'BR') {
      inlines.push({ type: 'text', text: '\n' })
      continue
    }
    const text = child.textContent || ''
    if (child.tagName === 'STRONG') inlines.push({ type: 'strong', text })
    else if (child.tagName === 'EM') inlines.push({ type: 'em', text })
    else if (child.tagName === 'CODE') inlines.push({ type: 'code', text })
    else if (child.tagName === 'SPAN') inlines.push({ type: 'text', text })
    else if (child.tagName === 'A') {
      const href = child.getAttribute('href') || ''
      if (!/^(https?:\/\/|mailto:)/.test(href)) return null
      inlines.push({ type: 'link', text, href })
    } else if (child.tagName === 'IMG') {
      const assetId = child.getAttribute('data-asset') || ''
      if (!/^[A-Za-z0-9_-]+$/.test(assetId)) return null
      inlines.push({ type: 'image', alt: child.getAttribute('alt') || '', assetId })
    } else return null
  }
  return inlines.length ? inlines : [{ type: 'text', text: '' }]
}

function Editable({ id, inlines, onInlines }: { id?: string; inlines: Inline[]; onInlines: (inlines: Inline[]) => void }) {
  const ref = useRef<HTMLDivElement>(null)
  const latest = useRef(inlines)
  latest.current = inlines
  useEffect(() => {
    const node = ref.current
    if (!node || document.activeElement === node) return
    node.replaceChildren(...(inlines.length ? inlines : [{ type: 'text', text: '' } as Inline]).map(domFor))
  }, [inlines])
  return (
    <div
      ref={ref}
      id={id}
      className="visual-block"
      contentEditable
      role="textbox"
      aria-multiline="true"
      dir="auto"
      suppressContentEditableWarning
      onPaste={event => {
        event.preventDefault()
        const text = event.clipboardData.getData('text/plain')
        const selection = window.getSelection()
        if (!selection || !selection.rangeCount || !ref.current) return
        selection.deleteFromDocument()
        selection.getRangeAt(0).insertNode(document.createTextNode(text))
        const next = inlinesFrom(ref.current)
        if (next) onInlines(next)
      }}
      onInput={() => {
        const next = ref.current ? inlinesFrom(ref.current) : null
        if (!next) {
          const node = ref.current
          if (node) node.replaceChildren(...latest.current.map(domFor))
          return
        }
        onInlines(next)
      }}
    />
  )
}

export function VisualMarkdown({ id, label, value, onChange }: Props) {
  const documentModel = parseRichText(value)
  if (!documentModel) return null
  function commit(blocks: Block[]) {
    const next = serializeRichText({ blocks })
    if (next !== value) onChange(next)
  }
  const blocks = documentModel.blocks.length ? documentModel.blocks : [{ type: 'paragraph', inlines: [{ type: 'text', text: '' }] } as Block]
  return (
    <div className="visual-markdown" role="group" aria-label={`${label} visual editor`}>
      {blocks.map((block, index) => {
        if (block.type === 'code') {
          return (
            <textarea
              key={index}
              className="visual-code"
              dir="auto"
              aria-label={`${label} code`}
              value={block.text}
              onChange={event => commit(blocks.map((item, itemIndex) => itemIndex === index && item.type === 'code' ? { ...item, text: event.target.value } : item))}
            />
          )
        }
        if (block.type === 'image') {
          return <p key={index} className="visual-image" dir="auto">Image: {block.alt} <code>asset:{block.assetId}</code></p>
        }
        if (block.type === 'bullet' || block.type === 'ordered') {
          return (
            <div key={index} className={block.type === 'bullet' ? 'visual-list' : 'visual-ordered'}>
              {block.items.map((item, itemIndex) => (
                <Editable
                  key={itemIndex}
                  inlines={item}
                  onInlines={next => commit(blocks.map((candidate, candidateIndex) => candidateIndex === index && (candidate.type === 'bullet' || candidate.type === 'ordered')
                    ? { ...candidate, items: candidate.items.map((current, currentIndex) => currentIndex === itemIndex ? next : current) }
                    : candidate))}
                />
              ))}
            </div>
          )
        }
        return (
          <div key={index} className={block.type === 'heading' ? `visual-heading visual-h${block.level}` : 'visual-paragraph'}>
            <Editable
              id={index === 0 ? id : undefined}
              inlines={block.inlines}
              onInlines={next => commit(blocks.map((candidate, candidateIndex) => candidateIndex === index && (candidate.type === 'paragraph' || candidate.type === 'heading')
                ? { ...candidate, inlines: next }
                : candidate))}
            />
          </div>
        )
      })}
    </div>
  )
}
