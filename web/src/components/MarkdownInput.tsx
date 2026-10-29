import { useEffect, useId, useRef, useState } from 'react'
import { Button } from './ui/button'
import { AssetPicker } from './AssetPicker'
import { Markdown } from './Markdown'
import { VisualMarkdown } from './VisualMarkdown'
import { formatRichText, parseRichText } from '../../../shared/richtext.mjs'
import type { Asset } from '../lib/api'

type Props = {
  label: string
  value: string
  onChange: (value: string) => void
  required?: boolean
  assets: Asset[]
  editable?: boolean
  projectId?: string
  id?: string
  error?: string
}

const ACTIONS = [
  ['Heading', 'heading'],
  ['Bold', 'bold'],
  ['Italic', 'italic'],
  ['Bullet list', 'bullet'],
  ['Numbered list', 'ordered'],
  ['Link', 'link'],
  ['Code block', 'code'],
] as const

export function MarkdownInput({
  label,
  value,
  onChange,
  required,
  assets,
  editable = false,
  projectId,
  id,
  error,
}: Props) {
  const generatedId = useId()
  const controlId = id || generatedId
  const input = useRef<HTMLTextAreaElement>(null)
  const [source, setSource] = useState(false)
  const [image, setImage] = useState('')
  const [alt, setAlt] = useState('')
  const [uploaded, setUploaded] = useState<Asset[]>([])
  const representable = parseRichText(value) !== null

  useEffect(() => {
    if (error) setSource(true)
  }, [error])

  useEffect(() => {
    setUploaded([])
    setImage('')
    setAlt('')
  }, [projectId])

  function insert(before: string, after = '', placeholder = 'text', replaceSelection = false) {
    const start = input.current?.selectionStart ?? value.length
    const end = input.current?.selectionEnd ?? start
    const selection = replaceSelection ? placeholder : value.slice(start, end) || placeholder
    onChange(value.slice(0, start) + before + selection + after + value.slice(end))
    requestAnimationFrame(() => {
      input.current?.focus()
      input.current?.setSelectionRange(start + before.length, start + before.length + selection.length)
    })
  }

  function format(action: typeof ACTIONS[number][1] | 'image') {
    if (!source && !representable) return
    if (source || !representable) {
      setSource(true)
      const syntax: Record<string, [string, string, string?]> = {
        heading: ['## ', '', 'text'],
        bold: ['**', '**', 'text'],
        italic: ['*', '*', 'text'],
        bullet: ['- ', '', 'text'],
        ordered: ['1. ', '', 'text'],
        link: ['[', '](https://example.com)', 'text'],
        code: ['\n```\n', '\n```\n', 'text'],
      }
      if (action === 'image') {
        insert(`![${alt.replace(/[\[\]\\]/g, '')}](`, ')', `asset:${image}`, true)
        return
      }
      const [before, after, placeholder] = syntax[action]
      insert(before, after, placeholder)
      return
    }
    const next = formatRichText(value, action, action === 'image' ? { alt, assetId: image } : undefined)
    if (next !== null) onChange(next)
  }

  const showVisual = !source && representable
  const showLocked = !source && !representable

  return (
    <section className="markdown-input">
      <label htmlFor={controlId}>{label}{required ? ' *' : ''}</label>
      <div className="markdown-toolbar" role="group" aria-label={`${label} formatting`}>
        {ACTIONS.map(([name, action]) => (
          <Button type="button" variant="outline" key={name} onClick={() => format(action)}>{name}</Button>
        ))}
        <Button type="button" variant="outline" aria-pressed={source} onClick={() => setSource(current => !current)}>
          {source ? 'Visual' : 'Source'}
        </Button>
      </div>
      {showLocked && (
        <div className="markdown-preview" dir="auto">
          <p className="notice" role="status">This content uses formatting the visual editor cannot represent. It was left unchanged. Edit the source to change it.</p>
          <Markdown text={value} assets={[...assets, ...uploaded]} />
        </div>
      )}
      {showVisual && <VisualMarkdown id={controlId} label={label} value={value} onChange={onChange} />}
      <textarea
        id={showVisual ? undefined : controlId}
        ref={input}
        rows={8}
        value={value}
        required={required}
        dir="auto"
        aria-label={showVisual ? undefined : label}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? `error-${controlId}` : undefined}
        onChange={event => onChange(event.target.value)}
        hidden={showVisual || showLocked}
      />
      <div className="inline-form">
        <AssetPicker
          label="Image asset"
          imagesOnly
          value={image}
          projectId={projectId}
          editable={editable}
          onUploaded={asset => setUploaded(previous => [...previous, asset])}
          onChange={next => setImage(next || '')}
        />
        <label>
          Image alt text
          <input value={alt} dir="auto" onChange={event => setAlt(event.target.value)} />
        </label>
        <Button type="button" variant="outline" disabled={!image || !alt.trim()} onClick={() => format('image')}>
          Insert image
        </Button>
      </div>
      <small>Markdown is saved as text. Images use durable asset IDs. Visual editing leaves unsupported source unchanged, and HTML is disabled.</small>
    </section>
  )
}
