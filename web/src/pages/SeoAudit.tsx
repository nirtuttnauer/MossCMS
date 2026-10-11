import { useEffect, useState } from 'react'
import { SearchCheck } from 'lucide-react'
import { Button } from '../components/ui/button'
import { Badge } from '../components/ui/badge'
import { getContext, gql, message, type ContentType } from '../lib/api'
import { seoAuditQuery, seoEntryLink, type SeoFinding, type SeoReport } from '../lib/seo'

export function SeoFindings({ findings, workspace, onField }: { findings: SeoFinding[]; workspace: string; onField?: (path: string | null) => void }) {
  return <ul className="seo-findings">{findings.map(f => <li key={`${f.entryId}:${f.code}:${f.fieldPath}:${f.locale}`}>
    <div className="seo-finding-meta"><Badge className={`seo-${f.severity}`}>{f.severity}</Badge><span>{f.locale || 'All locales'} · {f.snapshot} revision {f.revision}</span></div>
    {!onField && <h3>{f.entryTitle}</h3>}<p><strong>{f.explanation}</strong></p><p>{f.guidance}</p>
    {f.fieldPath && <code className="seo-field-path">{f.fieldPath}</code>}
    <div>{onField && f.fieldPath ? <Button type="button" variant="ghost" onClick={() => onField(f.fieldPath)}>Go to field</Button> : f.fieldPath ?
      <a className="text-link" href={seoEntryLink(f, workspace)}>Open {f.snapshot === 'live' ? 'draft to fix' : 'record'}</a> :
      <><a className="text-link" href={seoEntryLink(f, workspace)}>Open record</a> · <a className="text-link" href="#types">Review content type</a></>}</div>
  </li>)}</ul>
}

export function SeoMappings({ report }: { report: SeoReport }) {
  return <details className="plain-card seo-mappings"><summary>Detected field mappings</summary><ul>{report.mappings.map(m =>
    <li key={m.typeKey}><strong>{m.name}</strong> — {m.kind === 'supporting' ? 'Supporting content' : m.kind === 'needs_mapping' ? 'Needs mapping' : 'Page'}
      {m.kind !== 'supporting' && <p>Title: <code>{m.titlePath || 'Not detected'}</code> · Description: <code>{m.descriptionPath || 'Not detected'}</code></p>}</li>)}</ul>
    <p>Website types use their existing metadata fields and profile fallbacks. Custom types use the first recognized public field. Unknown mappings require review in <a href="#types">Content types</a>.</p></details>
}

export function SeoAudit({ types, projectId }: { types: ContentType[]; projectId: string }) {
  const [snapshot, setSnapshot] = useState<'draft' | 'live'>('live')
  const [type, setType] = useState('')
  const [severity, setSeverity] = useState('')
  const [cursors, setCursors] = useState<(string | null)[]>([null])
  const [refresh, setRefresh] = useState(0)
  const [report, setReport] = useState<SeoReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  useEffect(() => {
    let alive = true
    const context = getContext()
    setLoading(true); setError(''); setReport(null)
    gql<{ seoAudit: SeoReport }>(seoAuditQuery, { snapshot, type: type || null, severity: severity || null, after: cursors[cursors.length - 1] }, context)
      .then(result => { if (alive) setReport(result.seoAudit) })
      .catch(reason => { if (alive) setError(message(reason)) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [snapshot, type, severity, cursors, refresh, projectId])
  const rerun = () => { setCursors([null]); setRefresh(value => value + 1) }
  return <section className="seo-audit" aria-label="SEO audit">
    <header className="page-heading"><div><div className="eyebrow">CONTENT HEALTH</div><h1><SearchCheck size={28} aria-hidden="true" /> SEO audit</h1><p className="subtitle">Find record issues and follow clear guidance to fix them.</p></div><Button type="button" disabled={loading} onClick={rerun}>Rerun audit</Button></header>
    <p className="notice">Advisory record checks. A clean report means no findings in the checks evaluated; website SEO and rankings remain unverified. Captured schedules are excluded.</p>
    <div className="seo-filters"><label>Version<select value={snapshot} onChange={e => { setSnapshot(e.target.value as 'draft' | 'live'); setCursors([null]) }}><option value="live">Live</option><option value="draft">Drafts</option></select></label>
      <label>Content type<select value={type} onChange={e => { setType(e.target.value); setCursors([null]) }}><option value="">All types</option>{types.map(t => <option key={t.key} value={t.key}>{t.name}</option>)}</select></label>
      <label>Severity<select value={severity} onChange={e => { setSeverity(e.target.value); setCursors([null]) }}><option value="">All severities</option><option value="critical">Critical</option><option value="warning">Warning</option><option value="info">Informational</option></select></label></div>
    {loading && <p role="status">Checking {snapshot === 'live' ? 'live snapshots' : 'saved drafts'}…</p>}
    {error && <div className="form-error" role="alert">{error} <Button type="button" variant="outline" onClick={rerun}>Retry audit</Button></div>}
    {report && <>
      <section className="seo-summary plain-card" aria-label="Workspace audit summary"><h2>Workspace findings</h2><div className="seo-counts"><span><strong>{report.criticalCount}</strong> Critical</span><span><strong>{report.warningCount}</strong> Warnings</span><span><strong>{report.infoCount}</strong> Informational</span></div>
        <p>{report.recordCount} records inspected · {report.pageCount} pages · {report.supportingCount} supporting records · {report.needsMappingCount} need mapping</p>
        {snapshot === 'live' && report.noLiveCount > 0 && <p>{report.noLiveCount} records have no live snapshot and were excluded. Review them in Drafts.</p>}
        <small>Checked {new Date(report.generatedAt).toLocaleString()}. Counts cover the whole workspace; filters apply to findings below.</small></section>
      <section aria-label="SEO findings"><h2>Findings{type || severity ? ' matching filters' : ''} ({report.total})</h2>
        {!report.recordCount ? <p>No {snapshot === 'live' ? 'live records' : 'saved records'} to audit.</p> : !report.total ? <p>{type || severity ? 'No findings match these filters.' : 'No findings in the evaluated record checks. Review coverage and unchecked areas below.'}</p> : <SeoFindings findings={report.findings} workspace={projectId} />}
        <div className="inline-form seo-pagination"><Button type="button" variant="outline" disabled={cursors.length === 1} onClick={() => setCursors(previous => previous.slice(0, -1))}>Previous findings</Button><span>Page {cursors.length}</span><Button type="button" variant="outline" disabled={!report.hasNextPage} onClick={() => setCursors(previous => [...previous, report.endCursor])}>Next findings</Button></div></section>
      <SeoMappings report={report} />
      <section className="plain-card"><h2>Not checked</h2><p>{report.notChecked.join(' · ')}</p><p>Metadata length tips are review heuristics. External links are not fetched. Fixes to live findings must be saved into drafts and published.</p></section>
    </>}
  </section>
}
