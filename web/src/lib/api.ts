export type Field = { name: string; label?: string; type: string; required?: boolean; localized?: boolean; private?: boolean; fields?: Field[]; item?: Field; options?: string[]; target?: string }
export type ContentType = { id: string; key: string; name: string; fields: Field[]; version: number }
export type Entry = { id: string; typeKey: string; slug: string; title: string; data: Record<string, unknown>; status: string; version: number; updatedAt: string; scheduledAt?: string | null; isLive: boolean; hasUnpublishedChanges: boolean; publishedAt?: string | null; publishedRevision?: number | null; scheduledRevision?: number | null; scheduleError?: {code: string; message: string; revision: number; dueAt: string} | null }
export type Asset = { id: string; name: string; mime: string; size: number; url: string }
export type Project = { id: string; name: string; role: 'admin' | 'editor' | 'reader' }
export type Me = { user: { id: string; email: string; name: string }; csrf: string; projects: Project[]; providers: string[]; authSkipped?: boolean }
export type Provider = { id: string; name: string }
let current = { project: '', csrf: '' }
export function setContext(project: string, csrf: string) { current = { project, csrf } }
export async function rest<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const multipart = body instanceof FormData
  try {
    const response = await fetch(path, { method, credentials: 'include', signal: AbortSignal.timeout(multipart ? 120000 : 30000), headers: { 'X-Moss-Project': current.project, 'X-Moss-CSRF': current.csrf, ...(multipart ? {} : { 'Content-Type': 'application/json' }) }, body: body === undefined ? undefined : multipart ? body : JSON.stringify(body) })
    const result = await response.json()
    if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Request failed. Check the form values.')
    return result
  } catch (error) {
    if (error instanceof DOMException && error.name === 'TimeoutError') throw new Error('The request timed out. It may have completed; refresh the content before trying again.')
    throw error
  }
}
export async function gql<T>(query: string, variables?: Record<string, unknown>): Promise<T> {
  const result = await rest<{ data: T; errors?: { message: string }[] }>(import.meta.env.VITE_GRAPHQL_URL || '/graphql', 'POST', { query, variables })
  if (result.errors?.length) throw new Error(result.errors.map(error => error.message).join('\n'))
  return result.data
}
export const entryFields = 'id typeKey slug title data status version updatedAt scheduledAt isLive hasUnpublishedChanges publishedAt publishedRevision scheduledRevision scheduleError'
export const typeFields = 'id key name fields version'
export const saveEntryMutation = `mutation Save($typeKey:String!,$slug:String!,$data:JSON!,$status:String!,$id:ID,$version:Int,$scheduledAt:String){saveEntry(typeKey:$typeKey,slug:$slug,data:$data,status:$status,id:$id,version:$version,scheduledAt:$scheduledAt){${entryFields}}}`
export function slugify(value: string) { return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') }
export function message(error: unknown) { return error instanceof Error ? error.message : 'Something went wrong.' }

export const saveDraftMutation = `mutation Draft($requestKey:String!,$typeKey:String!,$slug:String!,$data:JSON!,$id:ID,$version:Int){saveDraft(requestKey:$requestKey,typeKey:$typeKey,slug:$slug,data:$data,id:$id,version:$version){${entryFields}}}`
export const draftReceiptQuery = `query Receipt($key:String!){draftReceipt(key:$key){${entryFields}}}`
