import { contentHash, readContentRoute } from './navigation'

export type SeoFinding = {
  code: string; severity: 'critical' | 'warning' | 'info'; entryId: string; entryTitle: string;
  typeKey: string; snapshot: 'draft' | 'live'; revision: number; locale: string | null;
  fieldPath: string | null; explanation: string; guidance: string;
}
export type SeoMapping = { typeKey: string; name: string; kind: string; titlePath: string | null; descriptionPath: string | null }
export type SeoReport = {
  snapshot: 'draft' | 'live'; generatedAt: string; revision: number | null;
  recordCount: number; pageCount: number; supportingCount: number; needsMappingCount: number; noLiveCount: number;
  criticalCount: number; warningCount: number; infoCount: number;
  mappings: SeoMapping[]; notChecked: string[]; findings: SeoFinding[];
  total: number; endCursor: string | null; hasNextPage: boolean;
}
export const seoReportFields = `snapshot generatedAt revision recordCount pageCount supportingCount needsMappingCount noLiveCount
  criticalCount warningCount infoCount mappings{typeKey name kind titlePath descriptionPath} notChecked
  findings{code severity entryId entryTitle typeKey snapshot revision locale fieldPath explanation guidance}
  total endCursor hasNextPage`
export const seoAuditQuery = `query($snapshot:String!,$type:String,$severity:String,$after:String){
  seoAudit(snapshot:$snapshot,typeKey:$type,severity:$severity,first:20,after:$after){${seoReportFields}}}`
export const seoEntryQuery = `query($id:ID!,$after:String){seoEntryAudit(id:$id,snapshot:"draft",first:20,after:$after){${seoReportFields}}}`
export function seoEntryLink(finding: SeoFinding, workspace: string) {
  return contentHash({ ...readContentRoute(undefined, '#content'), workspace, entry: finding.entryId,
    field: finding.fieldPath || '', seoSnapshot: finding.snapshot })
}
export function focusSeoField(path: string | null) {
  let target = path || ''
  while (target) {
    const element = document.getElementById(`field-${encodeURIComponent(target)}`)
    if (element) {
      element.scrollIntoView?.({ block: 'center' })
      const control = element as HTMLInputElement
      if (control.matches(':disabled')) {
        const group = element.closest('fieldset')
        if (group) { group.tabIndex = -1; group.focus() }
      } else element.focus()
      return
    }
    const parent = target.replace(/(?:\.[^.]+|\[\d+\])$/, '')
    if (parent === target || parent === 'data') break
    target = parent
  }
}
