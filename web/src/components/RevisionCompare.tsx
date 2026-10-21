import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { ArrowLeftRight, Info, RotateCcw, ShieldAlert } from 'lucide-react'
import { Badge } from './ui/badge'
import { Button } from './ui/button'
import { Dialog } from './ui/dialog'
import { Markdown } from './Markdown'
import { entryByIdQuery, getContext, gql, message, type Asset, type ContentType, type Entry } from '../lib/api'
import { buildRevisionDiffs, revisionValueIds } from '../lib/revisions'

export type Revision = {
  number: number
  snapshot: Record<string, unknown>
  author: string
  createdAt: string
}

type Props = {
  entry: Entry
  definition: ContentType
  revisions: Revision[]
  references: Entry[]
  assets: Asset[]
  role: string
  onClose: () => void
  onRestore: (revisionNumber: number) => Promise<void>
}

function formatScalar(val: unknown): string {
  if (val === null || val === undefined) return '(empty)'
  if (typeof val === 'boolean') return val ? 'true' : 'false'
  if (typeof val === 'object') return JSON.stringify(val)
  return String(val)
}

function resolveAssetLabel(assetId: unknown, assets: Asset[]): string {
  if (!assetId || typeof assetId !== 'string') return '(empty)'
  const found = assets.find(a => a.id === assetId)
  if (!found) return `Inaccessible asset (${assetId})`
  return `${found.name} (${found.mime}, ${Math.round(found.size / 1024)} KB)`
}

function resolveReferenceLabel(refId: unknown, references: Entry[]): string {
  if (!refId || typeof refId !== 'string') return '(empty)'
  const found = references.find(r => r.id === refId)
  if (!found) return `Deleted or inaccessible entry (${refId})`
  return `${found.title} (/${found.slug}) [${found.typeKey}]`
}

export function RevisionCompare({
  entry,
  definition,
  revisions,
  references,
  assets,
  role,
  onClose,
  onRestore,
}: Props) {
  const context = useRef(getContext()).current
  const [resolvedAssets, setResolvedAssets] = useState<Asset[]>([])
  const [resolvedReferences, setResolvedReferences] = useState<Entry[]>([])
  const [mode, setMode] = useState<'draft_live' | 'revisions'>('draft_live')
  const modeTabs = useRef<Record<typeof mode, HTMLButtonElement | null>>({ draft_live: null, revisions: null })
  const restoreOpener = useRef<HTMLButtonElement | null>(null)
  const [revANum, setRevANum] = useState<number>(() => revisions[1]?.number ?? revisions[0]?.number ?? 1)
  const [revBNum, setRevBNum] = useState<number>(() => revisions[0]?.number ?? entry.version)
  const [hideUnchanged, setHideUnchanged] = useState(false)
  const [rawView, setRawView] = useState(false)
  const [confirmRestoreRev, setConfirmRestoreRev] = useState<number | null>(null)
  const [restoreError, setRestoreError] = useState('')
  const [restoring, setRestoring] = useState(false)

  const editable = role !== 'reader'

  function handleTabKey(event: KeyboardEvent<HTMLButtonElement>) {
    let next: typeof mode
    if (event.key === 'Home') next = 'draft_live'
    else if (event.key === 'End') next = revisions.length >= 2 ? 'revisions' : 'draft_live'
    else if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') next = mode === 'draft_live' && revisions.length >= 2 ? 'revisions' : 'draft_live'
    else return
    event.preventDefault()
    setMode(next)
    modeTabs.current[next]?.focus()
  }

  function confirmRestore(number: number, opener: HTMLButtonElement) {
    restoreOpener.current = opener
    setConfirmRestoreRev(number)
  }

  function cancelRestore() {
    setConfirmRestoreRev(null)
    const opener = restoreOpener.current
    if (opener?.isConnected && !opener.disabled) opener.focus()
    else modeTabs.current[mode]?.focus()
  }

  // Prepare left and right data snapshots based on mode
  let leftMeta: { title: string; versionLabel: string; author?: string; time?: string; isLive?: boolean }
  let rightMeta: { title: string; versionLabel: string; author?: string; time?: string }
  let leftData: Record<string, unknown> = {}
  let rightData: Record<string, unknown> = {}
  let leftSlug = ''
  let rightSlug = ''
  let leftTitle = ''
  let rightTitle = ''

  if (mode === 'draft_live') {
    leftMeta = {
      title: 'Live Published Content',
      versionLabel: entry.publishedRevision ? `Revision ${entry.publishedRevision}` : 'Not published',
      author: revisions.find(revision => revision.number === entry.publishedRevision)?.author,
      time: entry.publishedAt ? new Date(entry.publishedAt).toLocaleString() : undefined,
      isLive: true,
    }
    rightMeta = {
      title: 'Current Saved Draft',
      versionLabel: `Version ${entry.version}`,
      author: revisions.find(revision => revision.number === entry.version)?.author,
      time: new Date(entry.updatedAt).toLocaleString(),
    }
    leftData = entry.publishedSnapshot?.data || entry.publishedData || {}
    rightData = entry.data || {}
    leftSlug = entry.publishedSnapshot?.slug || entry.publishedSlug || ''
    rightSlug = entry.slug || ''
    leftTitle = entry.publishedSnapshot?.title || entry.publishedTitle || ''
    rightTitle = entry.title || ''
  } else {
    const revA = revisions.find(r => r.number === revANum)
    const revB = revisions.find(r => r.number === revBNum)
    leftMeta = {
      title: `Revision ${revANum}`,
      versionLabel: `Version ${revANum}`,
      author: revA?.author,
      time: revA?.createdAt ? new Date(revA.createdAt).toLocaleString() : undefined,
    }
    rightMeta = {
      title: `Revision ${revBNum}`,
      versionLabel: `Version ${revBNum}`,
      author: revB?.author,
      time: revB?.createdAt ? new Date(revB.createdAt).toLocaleString() : undefined,
    }
    const snapA = (revA?.snapshot || {}) as Record<string, unknown>
    const snapB = (revB?.snapshot || {}) as Record<string, unknown>
    leftData = (snapA.data as Record<string, unknown>) || {}
    rightData = (snapB.data as Record<string, unknown>) || {}
    leftSlug = String(snapA.slug || '')
    rightSlug = String(snapB.slug || '')
    leftTitle = String(snapA.title || '')
    rightTitle = String(snapB.title || '')
  }

  const diffs = buildRevisionDiffs(
    definition.fields,
    { slug: leftSlug, title: leftTitle, data: leftData },
    { slug: rightSlug, title: rightTitle, data: rightData },
  )

  const referenceIds = revisionValueIds(diffs, 'reference')
  const assetIds = revisionValueIds(diffs, 'asset')
  useEffect(() => {
    let active = true
    for (const id of referenceIds.split(',').filter(Boolean)) {
      if (references.some(reference => reference.id === id)) continue
      gql<{ entry: Entry | null }>(entryByIdQuery, { id }, context)
        .then(result => {
          if (active && result.entry)
            setResolvedReferences(previous => [...previous.filter(reference => reference.id !== id), result.entry!])
        })
        .catch(() => {})
    }
    for (const id of assetIds.split(',').filter(Boolean)) {
      if (assets.some(asset => asset.id === id)) continue
      gql<{ assetPage: { nodes: Asset[] } }>('query($id:ID!){assetPage(id:$id,first:1)}', { id }, context)
        .then(result => {
          if (active && result.assetPage?.nodes)
            setResolvedAssets(previous => [...previous.filter(asset => asset.id !== id), ...result.assetPage.nodes])
        })
        .catch(() => {})
    }
    return () => { active = false }
  }, [referenceIds, assetIds, context, references, assets])

  const visibleDiffs = hideUnchanged ? diffs.filter(d => d.status !== 'unchanged') : diffs
  const changedCount = diffs.filter(d => d.status !== 'unchanged').length

  const handleExecuteRestore = async (num: number) => {
    setRestoring(true)
    setRestoreError('')
    try {
      await onRestore(num)
      setConfirmRestoreRev(null)
      onClose()
    } catch (reason) {
      setRestoreError(message(reason))
    } finally {
      setRestoring(false)
    }
  }

  const renderValueCell = (val: unknown, type: string) => {
    if (val === null || val === undefined) return <span className="diff-empty">(empty)</span>

    if (['richText', 'markdown'].includes(type) && typeof val === 'string') {
      return (
        <div className="diff-markdown" tabIndex={0}>
          <Markdown text={val} assets={[...assets, ...resolvedAssets]} />
        </div>
      )
    }

    if (type === 'asset') {
      return <span className="diff-asset">{resolveAssetLabel(val, [...assets, ...resolvedAssets])}</span>
    }

    if (type === 'reference') {
      return <span className="diff-ref">{resolveReferenceLabel(val, [...references, ...resolvedReferences])}</span>
    }

    if (typeof val === 'object') {
      return <pre tabIndex={0} className="diff-json">{JSON.stringify(val, null, 2)}</pre>
    }

    return <span>{formatScalar(val)}</span>
  }

  return (
    <Dialog title={`Compare revisions · ${entry.title}`} open onClose={onClose}>
      <div className="revision-compare-modal">
        {restoreError && <p className="form-error" role="alert">{restoreError}</p>}
        <p className="field-help">This comparison shows saved values. Unsaved form edits are excluded.</p>
        {/* Navigation & Mode Controls */}
        <div className="compare-toolbar">
          <div className="compare-mode-tabs" role="tablist" aria-label="Comparison mode">
            <button
              type="button"
              role="tab"
              ref={element => { modeTabs.current.draft_live = element }}
              tabIndex={mode === 'draft_live' ? 0 : -1}
              aria-selected={mode === 'draft_live'}
              className={`filter-button ${mode === 'draft_live' ? 'selected' : ''}`}
              onClick={() => setMode('draft_live')}
              onKeyDown={handleTabKey}
            >
              Draft vs Live content
            </button>
            <button
              type="button"
              role="tab"
              ref={element => { modeTabs.current.revisions = element }}
              tabIndex={mode === 'revisions' ? 0 : -1}
              aria-selected={mode === 'revisions'}
              className={`filter-button ${mode === 'revisions' ? 'selected' : ''}`}
              onClick={() => setMode('revisions')}
              onKeyDown={handleTabKey}
              disabled={revisions.length < 2}
            >
              Compare two saved revisions ({revisions.length})
            </button>
          </div>

          <div className="compare-options">
            <label className="checkbox-label text-sm">
              <input
                type="checkbox"
                checked={hideUnchanged}
                onChange={e => setHideUnchanged(e.target.checked)}
              />
              Hide unchanged fields ({diffs.length - changedCount})
            </label>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setRawView(prev => !prev)}
            >
              {rawView ? 'Structured view' : 'Raw JSON'}
            </Button>
          </div>
        </div>

        {/* Revision selectors when in revisions mode */}
        {mode === 'revisions' && (
          <div className="revision-picker-bar">
            <label>
              Left (Base):
              <select
                aria-label="Base revision"
                value={revANum}
                onChange={e => setRevANum(Number(e.target.value))}
              >
                {revisions.map(r => (
                  <option key={r.number} value={r.number}>
                    v{r.number} · {r.author} · {new Date(r.createdAt).toLocaleDateString()}
                  </option>
                ))}
              </select>
            </label>
            <ArrowLeftRight size={16} className="text-muted" aria-hidden="true" />
            <label>
              Right (Comparison):
              <select
                aria-label="Comparison revision"
                value={revBNum}
                onChange={e => setRevBNum(Number(e.target.value))}
              >
                {revisions.map(r => (
                  <option key={r.number} value={r.number}>
                    v{r.number} · {r.author} · {new Date(r.createdAt).toLocaleDateString()}
                  </option>
                ))}
              </select>
            </label>
          </div>
        )}

        {/* Revision side headers */}
        <div className="compare-headers-grid">
          <div className="compare-header-col left-col">
            <div className="col-title-row">
              <strong>{leftMeta.title}</strong>
              <Badge>{leftMeta.versionLabel}</Badge>
            </div>
            <div className="col-meta-row">
              {leftMeta.author && <span>By {leftMeta.author}</span>}
              {leftMeta.time && <span>{leftMeta.time}</span>}
              {!entry.isLive && mode === 'draft_live' && (
                <span className="text-muted italic">Entry is not published live yet</span>
              )}
            </div>
            {editable && mode === 'revisions' && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="mt-2"
                onClick={event => confirmRestore(revANum, event.currentTarget)}
              >
                <RotateCcw size={13} className="mr-1" />
                Restore v{revANum} as draft
              </Button>
            )}
            {editable && mode === 'draft_live' && entry.publishedRevision && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="mt-2"
                onClick={event => confirmRestore(entry.publishedRevision!, event.currentTarget)}
              >
                <RotateCcw size={13} className="mr-1" />
                Restore live revision (v{entry.publishedRevision}) as draft
              </Button>
            )}
          </div>

          <div className="compare-header-col right-col">
            <div className="col-title-row">
              <strong>{rightMeta.title}</strong>
              <Badge>{rightMeta.versionLabel}</Badge>
            </div>
            <div className="col-meta-row">
              {rightMeta.author && <span>By {rightMeta.author}</span>}
              {rightMeta.time && <span>{rightMeta.time}</span>}
            </div>
            {editable && mode === 'revisions' && revBNum !== entry.version && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="mt-2"
                onClick={event => confirmRestore(revBNum, event.currentTarget)}
              >
                <RotateCcw size={13} className="mr-1" />
                Restore v{revBNum} as draft
              </Button>
            )}
          </div>
        </div>

        {/* Restore confirmation alert */}
        {confirmRestoreRev !== null && (
          <div className="restore-confirm-banner" role="alert">
            <div className="restore-confirm-header">
              <Info size={16} />
              <strong>Confirm restore of Revision {confirmRestoreRev}</strong>
            </div>
            <p>
              Restoring Revision {confirmRestoreRev} will create a <strong>new draft</strong> (Version {entry.version + 1}) containing this revision’s content.
              Your currently live website content and any scheduled publications remain safe and unaffected.
              Current schema validations will apply to the restored draft.
            </p>
            <div className="inline-form mt-2">
              <Button
                type="button"
                disabled={restoring}
                onClick={() => handleExecuteRestore(confirmRestoreRev)}
              >
                {restoring ? 'Restoring draft…' : `Confirm and restore v${confirmRestoreRev} as draft`}
              </Button>
              <Button
                type="button"
                variant="outline"
                disabled={restoring}
                onClick={cancelRestore}
              >
                Cancel
              </Button>
            </div>
          </div>
        )}

        {!editable && (
          <p className="step-role-note my-2">
            <ShieldAlert size={14} /> Readers can inspect revision differences but cannot restore revisions.
          </p>
        )}

        {/* Comparison Content */}
        {rawView ? (
          <div className="compare-raw-view">
            <div className="raw-col">
              <h4>Left Snapshot</h4>
              <pre tabIndex={0}>{JSON.stringify({ slug: leftSlug, title: leftTitle, data: leftData }, null, 2)}</pre>
            </div>
            <div className="raw-col">
              <h4>Right Snapshot</h4>
              <pre tabIndex={0}>{JSON.stringify({ slug: rightSlug, title: rightTitle, data: rightData }, null, 2)}</pre>
            </div>
          </div>
        ) : (
          <div className="diff-table-wrap" tabIndex={0} role="region" aria-label="Revision differences">
            <table className="diff-table">
              <thead>
                <tr>
                  <th style={{ width: '25%' }}>FIELD</th>
                  <th style={{ width: '37.5%' }}>{leftMeta.title}</th>
                  <th style={{ width: '37.5%' }}>{rightMeta.title}</th>
                </tr>
              </thead>
              <tbody>
                {visibleDiffs.length === 0 ? (
                  <tr>
                    <td colSpan={3} className="text-center py-4 muted">
                      No differences found. All field values match.
                    </td>
                  </tr>
                ) : (
                  visibleDiffs.map(diff => (
                    <tr
                      key={diff.key}
                      className={`diff-row diff-${diff.status} ${diff.isRemovedField ? 'removed-field' : ''}`}
                    >
                      <td className="diff-label-cell">
                        <strong>{diff.label}</strong>
                        <div className="diff-status-pill">
                          <span className={`pill-badge ${diff.status}`}>{diff.status}</span>
                          <span className="diff-type">{diff.type}</span>
                        </div>
                      </td>
                      <td className="diff-val-cell left-val">
                        {renderValueCell(diff.leftVal, diff.type)}
                      </td>
                      <td className="diff-val-cell right-val">
                        {renderValueCell(diff.rightVal, diff.type)}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}

        <div className="modal-actions mt-4">
          <Button type="button" variant="outline" onClick={onClose}>
            Close comparison
          </Button>
        </div>
      </div>
    </Dialog>
  )
}
