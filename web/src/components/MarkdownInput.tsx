import { useEffect, useId, useRef, useState } from 'react'
import { Button } from './ui/button'
import { AssetPicker } from './AssetPicker'
import { Markdown } from './Markdown'
import { localeValueProps } from '../lib/locales'
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
  locale?: string
}

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
  locale,
}: Props) {
  const writing = localeValueProps(locale)
  const generatedId = useId()
  const controlId = id || generatedId
  const input = useRef<HTMLTextAreaElement>(null)
  const [preview, setPreview] = useState(false)
  const [image, setImage] = useState('')
  const [alt, setAlt] = useState('')
  const [uploaded, setUploaded] = useState<Asset[]>([])

  useEffect(() => {
    if (error) setPreview(false)
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

  return (
    <section className="markdown-input">
      <label htmlFor={controlId}>{label}{required ? ' *' : ''}</label>
      <div className="markdown-toolbar" role="group" aria-label={`${label} formatting`}>
        {[
          ['Heading', '## ', ''],
          ['Bold', '**', '**'],
          ['Italic', '*', '*'],
          ['Bullet list', '- ', ''],
          ['Numbered list', '1. ', ''],
          ['Link', '[', '](https://example.com)'],
          ['Code block', '\n```\n', '\n```\n'],
        ].map(([name, before, after]) => (
          <Button
            type="button"
            variant="outline"
            key={name}
            onClick={() => {
              setPreview(false)
              insert(before, after)
            }}
          >
            {name}
          </Button>
        ))}
        <Button
          type="button"
          variant="outline"
          aria-pressed={preview}
          onClick={() => setPreview(previous => !previous)}
        >
          {preview ? 'Edit Markdown' : 'Preview Markdown'}
        </Button>
      </div>
      <textarea
        id={controlId}
        ref={input}
        rows={8}
        value={value}
        required={required}
        dir={writing.dir}
        lang={writing.lang}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? `error-${controlId}` : undefined}
        onChange={event => onChange(event.target.value)}
        hidden={preview}
      />
      {preview && (
        <div className="markdown-preview" dir={writing.dir} lang={writing.lang}>
          <Markdown text={value} assets={[...assets, ...uploaded]} />
        </div>
      )}
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
          <input value={alt} dir={writing.dir} lang={writing.lang} onChange={event => setAlt(event.target.value)} />
        </label>
        <Button
          type="button"
          variant="outline"
          disabled={!image || !alt.trim()}
          onClick={() => {
            setPreview(false)
            insert(`![${alt.replace(/[\[\]\\]/g, '')}](`, ')', `asset:${image}`, true)
          }}
        >
          Insert image
        </Button>
      </div>
      <small>Markdown is saved as text. Images use durable asset IDs; HTML is disabled.</small>
    </section>
  )
}
