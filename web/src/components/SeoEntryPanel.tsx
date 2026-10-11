import { useEffect, useState } from 'react'
import { Button } from './ui/button'
import { getContext, gql, message, type Entry } from '../lib/api'
import { focusSeoField, seoEntryQuery, type SeoReport } from '../lib/seo'
import { SeoFindings, SeoMappings } from '../pages/SeoAudit'

export function SeoEntryPanel({ entry, dirty, projectId }: { entry: Entry | null; dirty: boolean; projectId: string }) {
  const [report, setReport] = useState<SeoReport | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const [cursors, setCursors] = useState<(string | null)[]>([null])
  useEffect(() => { setCursors(previous => previous.length > 1 ? [null] : previous) }, [entry?.id, entry?.version, projectId])
  useEffect(() => {
    if (!entry || entry.status === 'deleted') { setReport(null); return }
    let alive = true
    setLoading(true); setError(''); setReport(null)
    const context = getContext()
    gql<{ seoEntryAudit: SeoReport }>(seoEntryQuery, { id: entry.id, after: cursors[cursors.length - 1] }, context)
      .then(result => { if (alive) setReport(result.seoEntryAudit) })
      .catch(reason => { if (alive) setError(message(reason)) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [entry?.id, entry?.version, entry?.status, projectId, refresh, cursors])
  return <section className="editor-surface seo-entry-panel" aria-label="Saved draft SEO audit"><h2>SEO audit</h2>
    {!entry ? <p>Save this draft to check its SEO fields.</p> : entry.status === 'deleted' ? <p>Trashed records are excluded.</p> : <>
      <p>Saved draft{report?.revision != null ? ` revision ${report.revision}` : ` revision ${entry.version}`} · advisory checks</p>
      {dirty && <p className="notice" role="status">Results are stale while you have unsaved changes. They refresh after saving.</p>}
      {loading && <p role="status">Checking saved draft…</p>}
      {error && <p className="form-error" role="alert">{error}</p>}
      {report && <><p>{report.criticalCount} critical · {report.warningCount} warnings · {report.infoCount} informational</p>
        {report.total ? <SeoFindings findings={report.findings} workspace={projectId} onField={focusSeoField} /> : <p>No findings in the evaluated record checks.</p>}
        {report.hasNextPage && <Button type="button" variant="outline" onClick={() => setCursors(previous => [...previous, report.endCursor])}>More findings</Button>}
        {cursors.length > 1 && <Button type="button" variant="outline" onClick={() => setCursors(previous => previous.slice(0, -1))}>Previous findings</Button>}
        <SeoMappings report={report} /></>}
      <Button type="button" variant="outline" disabled={loading} onClick={() => { setCursors([null]); setRefresh(value => value + 1) }}>Recheck saved draft</Button>
    </>}
    <p><a href="#seo">Open workspace SEO audit</a></p><p className="field-help">Website HTML and indexing are not checked. Captured schedules are excluded.</p>
  </section>
}
