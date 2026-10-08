export type Field = { imageOnly?: boolean; name: string; label?: string; type: string; required?: boolean; localized?: boolean; private?: boolean; fields?: Field[]; item?: Field; options?: string[]; target?: string }
export type ContentType = { entryCount?:number; id: string; key: string; name: string; fields: Field[]; version: number }
export type Entry = { id: string; typeKey: string; slug: string; title: string; data: Record<string, unknown>; status: string; version: number; updatedAt: string; scheduledAt?: string | null; isLive: boolean; hasUnpublishedChanges: boolean; publishedAt?: string | null; publishedRevision?: number | null; scheduledRevision?: number | null; scheduleError?: {code: string; message: string; revision: number; dueAt: string;failedAt?:string} | null }
export type Asset = { width?:number|null; height?:number|null; variants?: {width:number;height:number;size:number;url:string}[]; id: string; name: string; mime: string; size: number; url: string }
export type Project = { previewOrigin?: string | null; id: string; name: string; role: 'admin' | 'editor' | 'reader' }
export type Me = { user: { id: string; email: string; name: string }; csrf: string; projects: Project[]; providers: string[]; authSkipped?: boolean }
export type Provider = { id: string; name: string }
let current = { project: '', csrf: '' }
export function setContext(project: string, csrf: string) { current = { project, csrf } }
export function getContext() { return {...current} }
export class ApiError extends Error {
  constructor(message: string, public code = 'REQUEST_FAILED', public requestId?: string, public uncertain = false) { super(message) }
}
export async function rest<T>(path: string, method = 'GET', body?: unknown, context = getContext()): Promise<T> {
  const multipart = body instanceof FormData
  try {
    const response = await fetch(path, { method, credentials: 'include', signal: AbortSignal.timeout(multipart ? 120000 : 30000), headers: { 'X-Moss-Project': context.project, 'X-Moss-CSRF': context.csrf, ...(multipart ? {} : { 'Content-Type': 'application/json' }) }, body: body === undefined ? undefined : multipart ? body : JSON.stringify(body) })
    const result = await response.json()
    if (!response.ok) throw new ApiError(typeof result.detail === 'string' ? result.detail : 'Request failed. Check the form values.', result.code, response.headers?.get('X-Request-ID') || undefined)
    return result
  } catch (error) {
    if (error instanceof DOMException && error.name === 'TimeoutError') throw new ApiError('The request timed out. Its outcome is being checked.', 'TIMEOUT', undefined, method !== 'GET')
    if (error instanceof TypeError) throw new ApiError('Connection lost. Your edits are retained.', 'NETWORK', undefined, method !== 'GET')
    throw error
  }
}
export async function gql<T>(query: string, variables?: Record<string, unknown>, context = getContext()): Promise<T> {
  const result = await rest<{ data: T; errors?: { message: string; extensions?: {code?: string; requestId?: string} }[] }>(import.meta.env.VITE_GRAPHQL_URL || '/graphql', 'POST', { query, variables }, context)
  if (result.errors?.length) throw new ApiError(result.errors.map(error => error.message).join('\n'), result.errors[0].extensions?.code, result.errors[0].extensions?.requestId)
  return result.data
}
export const entryFields = 'id typeKey slug title data status version updatedAt scheduledAt isLive hasUnpublishedChanges publishedAt publishedRevision scheduledRevision scheduleError'
export const typeFields = 'id key name fields version entryCount'
export const saveEntryMutation = `mutation Save($typeKey:String!,$slug:String!,$data:JSON!,$status:String!,$id:ID,$version:Int,$scheduledAt:String,$requestKey:String){saveEntry(typeKey:$typeKey,slug:$slug,data:$data,status:$status,id:$id,version:$version,scheduledAt:$scheduledAt,requestKey:$requestKey){${entryFields}}}`
export function slugify(value: string) { return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') }
export function message(error: unknown) { return error instanceof ApiError && (error.requestId || error.code !== 'REQUEST_FAILED') ? `${error.message} (${error.code}${error.requestId ? ` · request ${error.requestId}` : ''})` : error instanceof Error ? error.message : 'Something went wrong.' }

export const saveDraftMutation = `mutation Draft($requestKey:String!,$typeKey:String!,$slug:String!,$data:JSON!,$id:ID,$version:Int){saveDraft(requestKey:$requestKey,typeKey:$typeKey,slug:$slug,data:$data,id:$id,version:$version){${entryFields}}}`
export const draftReceiptQuery = `query Receipt($key:String!){draftReceipt(key:$key){${entryFields}}}`
