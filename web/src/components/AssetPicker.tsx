import { useEffect, useId, useRef, useState } from 'react'
import { ApiError, getContext, gql, message, rest, type Asset } from '../lib/api'
import { Button } from './ui/button'
import { Dialog } from './ui/dialog'

export const assetPageQuery = 'query($after:String,$search:String!,$imagesOnly:Boolean!,$id:ID){assetPage(first:24,after:$after,search:$search,imagesOnly:$imagesOnly,id:$id)}'
type Page = {
  nodes: Asset[]
  endCursor: string | null
  hasNextPage: boolean
}
type Props = {
  label: string
  value: string
  onChange: (id: string | null) => void
  imagesOnly?: boolean
  editable?: boolean
  projectId?: string
  id?: string
  error?: string
  onUploaded?: (asset: Asset) => void
}
const emptyPage: Page = { nodes: [], endCursor: null, hasNextPage: false }
const MAX_UPLOAD = 20 * 1024 * 1024
const ASSET_SEARCH_DEBOUNCE_MS = 200
const ALT_WARNING_TITLE = 'Add alternative text before you insert this image'

function isLibraryImage(asset: Asset, imagesOnly: boolean) {
  return imagesOnly || asset.mime.toLowerCase().startsWith('image/')
}

function visibleLabel(element: HTMLElement) {
  const copy = element.cloneNode(true) as HTMLElement
  copy.querySelectorAll('input, textarea, select').forEach(node => node.remove())
  return (copy.textContent || '').replace(/\s+/g, ' ').replace(/\s*\*$/, '').trim().toLowerCase()
}

function controlValue(label: HTMLElement) {
  const control = label.querySelector('input, textarea')
  if (control instanceof HTMLInputElement || control instanceof HTMLTextAreaElement) return control.value
  return ''
}

// Markdown insert stays disabled until alternative text is present, so selection there is not a second gate.
function markdownAlreadyRequiresAlt(root: HTMLElement) {
  const host = root.parentElement
  if (!host) return false
  const labels = [...host.querySelectorAll('label')].filter(label => !root.contains(label))
  const hasAlt = labels.some(label => visibleLabel(label) === 'image alt text')
  const hasInsert = [...host.querySelectorAll('button')].some(button => !root.contains(button) && (button.textContent || '').trim() === 'Insert image')
  return hasAlt && hasInsert
}

function siblingAltText(root: HTMLElement) {
  const group = root.closest('fieldset.field-group')
  if (!(group instanceof HTMLElement)) return null
  const direct = [...group.querySelectorAll('label')].filter(label => {
    if (root.contains(label)) return false
    return label.closest('fieldset.field-group') === group
  })
  for (const label of direct) {
    const name = visibleLabel(label)
    if (name === 'alt' || name === 'alternative text' || name === 'alt text') return controlValue(label)
  }
  const nested = [...group.querySelectorAll('fieldset.field-group')].filter(fieldset => {
    if (!(fieldset instanceof HTMLElement) || fieldset === group || root.contains(fieldset)) return false
    if (fieldset.parentElement?.closest('fieldset.field-group') !== group) return false
    const legend = [...fieldset.children].find(child => child instanceof HTMLElement && child.tagName === 'LEGEND')
    return legend instanceof HTMLElement && visibleLabel(legend) === 'alt'
  })
  if (nested.length === 0) return null
  const values = nested.flatMap(fieldset => [...fieldset.querySelectorAll('input, textarea')].flatMap(control => (
    control instanceof HTMLInputElement || control instanceof HTMLTextAreaElement ? [control.value] : []
  )))
  return values.find(value => value.trim()) ?? ''
}

function needsAltWarning(root: HTMLElement | null, asset: Asset, imagesOnly: boolean) {
  if (!isLibraryImage(asset, imagesOnly)) return false
  if (root && markdownAlreadyRequiresAlt(root)) return false
  if (!root) return true
  const alt = siblingAltText(root)
  return alt === null || alt.trim() === ''
}

export function AssetPicker({
  label,
  value,
  onChange,
  imagesOnly = false,
  editable = false,
  projectId,
  id,
  error: fieldError,
  onUploaded,
}: Props) {
  const generatedId = useId()
  const controlId = id || generatedId
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [cursors, setCursors] = useState<(string | null)[]>([null])
  const [page, setPage] = useState<Page>(emptyPage)
  const [selected, setSelected] = useState<Asset | null>(null)
  const [error, setError] = useState('')
  const [uploadError, setUploadError] = useState('')
  const [status, setStatus] = useState('')
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [retry, setRetry] = useState(0)
  const uploadInput = useRef<HTMLInputElement>(null)
  const pickerRoot = useRef<HTMLElement>(null)
  const uploadEpoch = useRef(0)
  const latestUpload = useRef(0)
  const mounted = useRef(true)
  const [pendingImage, setPendingImage] = useState<Asset | null>(null)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      uploadEpoch.current++
    }
  }, [])
  useEffect(() => {
    uploadEpoch.current++
  }, [editable])
  useEffect(() => {
    uploadEpoch.current++
    setOpen(false)
    setSearch('')
    setCursors([null])
    setPage(emptyPage)
    setError('')
    setUploadError('')
    setStatus('')
    setBusy(false)
    setPendingImage(null)
  }, [projectId, imagesOnly])
  useEffect(() => {
    let active = true
    const context = getContext()
    setSelected(null)
    if (value) {
      gql<{ assetPage: Page }>(assetPageQuery, { id: value, search: '', imagesOnly, after: null }, context)
        .then(result => {
          if (active && getContext().project === context.project) {
            setSelected(result.assetPage.nodes[0] || null)
          }
        })
        .catch(reason => {
          if (active && getContext().project === context.project) {
            setError(message(reason))
          }
        })
    }
    return () => {
      active = false
    }
  }, [value, imagesOnly, projectId])
  useEffect(() => {
    if (!open) {
      return
    }
    let active = true
    const context = getContext()
    setLoading(true)
    setError('')
    const timer = setTimeout(() => {
      gql<{ assetPage: Page }>(assetPageQuery, { search, imagesOnly, after: cursors[cursors.length - 1] }, context)
        .then(result => {
          if (active && getContext().project === context.project) {
            setPage(result.assetPage)
          }
        })
        .catch(reason => {
          if (active && getContext().project === context.project) {
            setError(message(reason))
          }
        })
        .finally(() => {
          if (active && getContext().project === context.project) {
            setLoading(false)
          }
        })
    }, ASSET_SEARCH_DEBOUNCE_MS)
    return () => {
      active = false
      clearTimeout(timer)
    }
  }, [search, cursors, open, imagesOnly, projectId, retry])

  async function upload(file?: File) {
    if (!file || !editable || busy || !open) {
      return
    }
    setUploadError('')
    setStatus('')
    if (!file.size || file.size > MAX_UPLOAD) {
      setUploadError('Choose a file of 1 byte to 20 MiB.')
      return
    }
    if (imagesOnly && !/\.(png|jpe?g|webp)$/i.test(file.name)) {
      setUploadError('Choose a JPEG, PNG or WebP image.')
      return
    }
    const context = getContext()
    const epoch = ++uploadEpoch.current
    const operation = ++latestUpload.current
    const stillCurrent = () => mounted.current && epoch === uploadEpoch.current && getContext().project === context.project
    setBusy(true)
    try {
      const form = new FormData()
      form.append('file', file)
      form.append('imagesOnly', String(imagesOnly))
      const asset = await rest<Asset>('/api/assets', 'POST', form, context)
      if (stillCurrent()) {
        setSelected(asset)
        onUploaded?.(asset)
        onChange(asset.id)
        setStatus(`Uploaded and selected ${asset.name}.`)
        setOpen(false)
        requestAnimationFrame(() => document.getElementById(controlId)?.focus())
      }
    } catch (reason) {
      if (stillCurrent()) {
        setUploadError(reason instanceof ApiError && reason.uncertain
          ? `${message(reason)} The upload may have succeeded. Search the media library for this filename before uploading again.`
          : message(reason))
      }
    } finally {
      if (mounted.current && operation === latestUpload.current && getContext().project === context.project) {
        setBusy(false)
      }
      if (operation === latestUpload.current && uploadInput.current) {
        uploadInput.current.value = ''
      }
    }
  }

  function commit(asset: Asset) {
    onChange(asset.id)
    setSelected(asset)
    setPendingImage(null)
    setOpen(false)
    requestAnimationFrame(() => document.getElementById(controlId)?.focus())
  }

  function choose(asset: Asset) {
    if (needsAltWarning(pickerRoot.current, asset, imagesOnly)) {
      setPendingImage(asset)
      return
    }
    commit(asset)
  }

  return <section ref={pickerRoot} className="asset-picker" aria-label={`Asset picker for ${label}`}>
    <strong>{label}</strong>
    <div className="inline-form">
      {selected?.variants?.[0] && <img
        src={selected.variants[0].url}
        alt=""
        width={80}
        height={60}
        style={{ objectFit: 'cover' }}
      />}
      <span>{selected?.name || (value ? 'Selected asset unavailable' : 'No asset selected')}</span>
      <Button
        id={controlId}
        aria-invalid={Boolean(fieldError)}
        aria-describedby={fieldError ? `error-${controlId}` : undefined}
        type="button"
        variant="outline"
        aria-expanded={open}
        onClick={() => {
          if (open) {
            uploadEpoch.current++
            setPendingImage(null)
          }
          setOpen(previous => !previous)
        }}
      >{open ? 'Close selection' : 'Choose asset'}</Button>
      {value && <Button type="button" variant="outline" disabled={busy} onClick={() => onChange(null)}>Clear</Button>}
    </div>
    {open && <>
      {editable && <div className="inline-form">
        <input
          ref={uploadInput}
          type="file"
          tabIndex={-1}
          className="sr-only"
          aria-label={`Upload ${label}`}
          accept={imagesOnly ? '.jpg,.jpeg,.png,.webp' : undefined}
          disabled={busy}
          onChange={event => {
            void upload(event.target.files?.[0])
            event.target.value = ''
          }}
        />
        <Button
          type="button"
          variant="outline"
          disabled={busy}
          onClick={() => uploadInput.current?.click()}
        >{busy ? 'Uploading…' : 'Upload asset'}</Button>
        <small>{imagesOnly ? 'JPEG, PNG or WebP. ' : ''}Files up to 20 MiB.</small>
      </div>}
      <label>Search assets<input
        value={search}
        onChange={event => {
          setSearch(event.target.value)
          setCursors([null])
        }}
      /></label>
      <p role="status">{loading ? 'Loading assets…'
        : error ? ''
        : page.nodes.length
          ? `Showing ${page.nodes.length} assets.${page.hasNextPage ? ' More available with Next assets.' : ''}`
          : 'No matching assets.'}</p>
      {!loading && !error && <div className="asset-grid">
        {page.nodes.map(asset => <button
          type="button"
          key={asset.id}
          disabled={busy}
          aria-pressed={value === asset.id}
          onClick={() => choose(asset)}
        >
          {asset.variants?.[0] && <img
            src={asset.variants[0].url}
            alt=""
            width={120}
            height={80}
            loading="lazy"
            style={{ objectFit: 'cover' }}
          />}
          <span>{asset.name}</span>
        </button>)}
      </div>}
      <Button
        type="button"
        variant="outline"
        disabled={cursors.length === 1 || loading || busy || Boolean(error)}
        onClick={() => setCursors(previous => previous.slice(0, -1))}
      >Previous assets</Button>
      <Button
        type="button"
        variant="outline"
        disabled={!page.hasNextPage || loading || busy || Boolean(error)}
        onClick={() => setCursors(previous => [...previous, page.endCursor])}
      >Next assets</Button>
      {error && <div role="alert">
        <p>{error}</p>
        <Button
          type="button"
          variant="outline"
          onClick={() => setRetry(previous => previous + 1)}
        >Retry asset search</Button>
      </div>}
    </>}
    {busy && <p role="status">Uploading asset…</p>}
    {uploadError && <p role="alert">{uploadError}</p>}
    {status && <p role="status">{status}</p>}
    {!open && error && <p role="alert">{error}</p>}
    <Dialog title={ALT_WARNING_TITLE} open={pendingImage !== null} onClose={() => setPendingImage(null)}>
      <p role="alert">Alternative text is missing for this image. The asset picker flags common accessibility problems before you publish.</p>
      <div className="row-actions">
        <Button type="button" variant="outline" onClick={() => setPendingImage(null)}>Go back</Button>
        <Button type="button" onClick={() => { if (pendingImage) commit(pendingImage) }}>Insert without alternative text</Button>
      </div>
    </Dialog>
  </section>
}
