import { ApiError, getContext, type Field } from './api'

export type TransformStep = { op: 'rename' | 'default' | 'drop' | 'convert'; path: string; typeKey: string; argument: string }
export type MigrationReport = {
  applied: boolean; alreadyImported?: boolean; validation: string; importKey: string;
  counts: { schemas: number; entries: number; assets: number; revisions: number; provenance: number };
  omittedFields: string[]; includePrivate: boolean; publication: string;
  sourceSchemas: { key: string; name: string; fields: Field[]; version: number }[];
  transformations: { entryId: string; snapshot: string; step: number; op: string; path: string }[];
}

export function buildPipeline(steps: TransformStep[], schemas: string) {
  let overrides: unknown
  try { overrides = JSON.parse(schemas || '{}') } catch { throw new Error('Destination schemas must be valid JSON.') }
  if (!overrides || typeof overrides !== 'object' || Array.isArray(overrides)) throw new Error('Destination schemas must be an object keyed by content type.')
  return { schemas: overrides, steps: steps.map((step, index) => {
    if (!step.path.trim()) throw new Error(`Step ${index + 1}: enter a field path.`)
    const common = { op: step.op, path: step.path.trim(), ...(step.typeKey.trim() ? { typeKey: step.typeKey.trim() } : {}) }
    if (step.op === 'drop') return common
    if (step.op === 'default') {
      try { return { ...common, value: JSON.parse(step.argument) as unknown } }
      catch { throw new Error(`Step ${index + 1}: default value must be JSON, such as "Untitled", 0, or false.`) }
    }
    if (!step.argument.trim()) throw new Error(`Step ${index + 1}: choose a destination ${step.op === 'rename' ? 'field' : 'type'}.`)
    return { ...common, to: step.argument.trim() }
  }) }
}

export async function exportArchive(history: boolean, includePrivate: boolean, context = getContext()) {
  const body = new FormData()
  body.set('history', String(history)); body.set('includePrivate', String(includePrivate))
  let response: Response
  try {
    response = await fetch('/api/migration/export', { method: 'POST', credentials: 'include', signal: AbortSignal.timeout(300_000),
      headers: { 'X-Moss-Project': context.project, 'X-Moss-CSRF': context.csrf }, body })
  } catch { throw new Error('Export connection was interrupted. Try downloading the archive again.') }
  if (!response.ok) {
    const error = await response.json() as { detail?: string; code?: string }
    throw new ApiError(error.detail || 'Export failed.', error.code, response.headers.get('X-Request-ID') || undefined)
  }
  const archive = await response.blob()
  const url = URL.createObjectURL(archive)
  const link = document.createElement('a')
  link.href = url; link.download = `moss-workspace-${context.project}.zip`
  document.body.append(link); link.click(); link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
