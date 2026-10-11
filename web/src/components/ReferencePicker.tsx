import { useEffect, useId, useState } from 'react'
import { entryByIdQuery, entryFields, getContext, gql, message, type Entry } from '../lib/api'
import { Button } from './ui/button'

export const referenceEntriesQuery = `query($typeKey:String,$search:String!,$after:String,$first:Int){entries(typeKey:$typeKey,search:$search,after:$after,first:$first){nodes{${entryFields}} total endCursor hasNextPage}}`

const REFERENCE_SEARCH_DEBOUNCE_MS = 200
const REFERENCE_PAGE_SIZE = 20

type Page = {
  nodes: Entry[]
  total: number
  endCursor: string | null
  hasNextPage: boolean
}

type Props = {
  label: string
  value: string | null
  onChange: (id: string | null) => void
  target?: string
  required?: boolean
  initialReferences?: Entry[]
  projectId?: string
  editable?: boolean
  id?: string
  error?: string
}

export function ReferencePicker({
  label,
  value,
  onChange,
  target,
  required,
  initialReferences,
  projectId,
  id,
  error: fieldError,
}: Props) {
  const generatedId = useId()
  const controlId = id || generatedId
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [cursors, setCursors] = useState<(string | null)[]>([null])
  const initialNodes = (initialReferences || []).filter(e => !target || e.typeKey === target)
  const [page, setPage] = useState<Page>({
    nodes: initialNodes,
    total: initialNodes.length,
    endCursor: null,
    hasNextPage: false,
  })
  const [selected, setSelected] = useState<Entry | null>(null)
  const [selectedUnavailable, setSelectedUnavailable] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    setOpen(false)
    setSearch('')
    setCursors([null])
    setError('')
    setPage({ nodes: [], total: 0, endCursor: null, hasNextPage: false })
  }, [projectId, target])

  useEffect(() => {
    let active = true
    const context = getContext()
    const local = initialReferences?.find(
      entry => entry.id === value && (!target || entry.typeKey === target),
    )
    setSelected(local || null)
    setSelectedUnavailable(false)
    if (value) {
      gql<{ entry: Entry | null }>(entryByIdQuery, { id: value }, context)
        .then(result => {
          if (!active || getContext().project !== context.project) {
            return
          }
          const entry = result.entry
          const matches = entry && (!target || entry.typeKey === target)
          setSelected(matches ? entry : null)
          setSelectedUnavailable(!matches || entry?.status === 'deleted')
        })
        .catch(() => {
          if (active && getContext().project === context.project) {
            setSelected(null)
            setSelectedUnavailable(true)
          }
        })
    }
    return () => {
      active = false
    }
  }, [value, projectId, target, initialReferences])

  useEffect(() => {
    if (!open) {
      return
    }
    let active = true
    const context = getContext()
    setLoading(true)
    setError('')
    const timer = setTimeout(() => {
      gql<{ entries: Page }>(referenceEntriesQuery, {
        typeKey: target || null,
        search,
        after: cursors[cursors.length - 1],
        first: REFERENCE_PAGE_SIZE,
      }, context)
        .then(res => {
          if (active && getContext().project === context.project && res?.entries) {
            setPage(res.entries)
            setError('')
          }
        })
        .catch(err => {
          if (active && getContext().project === context.project) {
            setError(message(err))
          }
        })
        .finally(() => {
          if (active && getContext().project === context.project) {
            setLoading(false)
          }
        })
    }, REFERENCE_SEARCH_DEBOUNCE_MS)

    return () => {
      active = false
      clearTimeout(timer)
    }
  }, [open, target, search, cursors, refreshKey, projectId])

  return (
    <section className="reference-picker" aria-label={`Reference picker for ${label}`}>
      <strong>{label}{required ? ' *' : ''}</strong>
      <div className="inline-form">
        {selected ? (
          <div className="reference-summary">
            <strong>{selected.title}</strong>
            <span className={`content-type-label ${selected.typeKey}`}>({selected.typeKey})</span>
            <span className={`badge ${selected.status === 'deleted' ? 'deleted' : selected.isLive ? 'published' : 'draft'}`}>
              {selected.status === 'deleted' ? 'In trash' : selected.isLive ? 'Live' : 'Draft'}
            </span>
          </div>
        ) : selectedUnavailable ? (
          <span className="reference-unavailable" role="status">
            Selected target unavailable ({value})
          </span>
        ) : (
          <span className="muted" role={value ? 'status' : undefined}>
            {value ? 'Loading selected reference…' : 'No entry selected'}
          </span>
        )}
        <Button
          type="button"
          variant="outline"
          id={controlId}
          aria-invalid={Boolean(fieldError)}
          aria-describedby={fieldError ? `error-${controlId}` : undefined}
          aria-expanded={open}
          onClick={() => setOpen(v => !v)}
        >
          {open ? 'Close reference picker' : 'Choose reference'}
        </Button>
        {value && (
          <Button type="button" variant="outline" onClick={() => onChange(null)}>
            Clear
          </Button>
        )}
      </div>

      {selected && !selected.isLive && selected.status !== 'deleted' && (
        <small className="field-help" role="status">
          Draft target: will not resolve in public delivery until published.
        </small>
      )}

      {selectedUnavailable && (
        <small className="form-error" role="status">
          The selected entry is deleted or inaccessible. Clear the selection or choose a replacement.
        </small>
      )}

      {open && (
        <div className="reference-picker-panel">
          <label>
            Search {target ? `${target} entries` : 'entries'}
            <input
              aria-label="Search reference targets"
              placeholder="Search by title or slug…"
              value={search}
              onChange={e => {
                setSearch(e.target.value)
                setCursors([null])
              }}
            />
          </label>

          <p role="status">
            {loading
              ? 'Loading reference targets…'
              : error
                ? ''
                : page.nodes.length
                  ? `Showing ${page.nodes.length} of ${page.total} matching entries.`
                  : 'No matching entries.'}
          </p>

          {error && (
            <div role="alert" className="form-error">
              <p>{error}</p>
              <Button type="button" variant="outline" onClick={() => setRefreshKey(k => k + 1)}>
                Retry
              </Button>
            </div>
          )}

          <div className="reference-results" aria-label="Reference targets">
            {!loading && !error && page.nodes
              .filter(entry => entry.status !== 'deleted' && (!target || entry.typeKey === target))
              .map(entry => {
                const isCurrent = value === entry.id
                return (
                  <button
                    type="button"
                    aria-pressed={isCurrent}
                    key={entry.id}
                    className={`reference-item ${isCurrent ? 'selected' : ''}`}
                    onClick={() => {
                      onChange(entry.id)
                      setSelected(entry)
                      setSelectedUnavailable(false)
                      setOpen(false)
                      requestAnimationFrame(() => document.getElementById(controlId)?.focus())
                    }}
                  >
                    <div className="reference-item-main">
                      <strong>{entry.title}</strong>
                      <span className="entry-slug">/{entry.slug}</span>
                    </div>
                    <div className="reference-item-meta">
                      <span className={`content-type-label ${entry.typeKey}`}>{entry.typeKey}</span>
                      <span className={`badge ${entry.isLive ? 'published' : 'draft'}`}>
                        {entry.isLive ? 'Live' : 'Draft'}
                      </span>
                    </div>
                  </button>
                )
              })}
          </div>

          <div className="pagination">
            <Button
              type="button"
              variant="outline"
              disabled={cursors.length === 1 || loading || Boolean(error)}
              onClick={() => setCursors(c => c.slice(0, -1))}
            >
              Previous references
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={!page.hasNextPage || loading || Boolean(error)}
              onClick={() => setCursors(c => [...c, page.endCursor])}
            >
              Next references
            </Button>
          </div>
        </div>
      )}
    </section>
  )
}
