import { useEffect, useId, useRef, useState } from 'react'
import { ApiError, getContext, gql, message, rest, type Asset } from '../lib/api'
import { Button } from './ui/button'

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
  const uploadEpoch = useRef(0)
  const latestUpload = useRef(0)
  const mounted = useRef(true)

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

  return <section className="asset-picker" aria-label={`Asset picker for ${label}`}>
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
          onClick={() => {
            onChange(asset.id)
            setSelected(asset)
            setOpen(false)
            requestAnimationFrame(() => document.getElementById(controlId)?.focus())
          }}
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
  </section>
}
