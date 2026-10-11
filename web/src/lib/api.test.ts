import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getContext, gql, rest, saveContentTypeMutation, setContext } from './api'

const fetchMock = vi.fn<typeof fetch>()

function response(result: unknown, ok = true, requestId?: string) {
  return {
    ok,
    json: async () => result,
    headers: new Headers(requestId ? { 'X-Request-ID': requestId } : {}),
  } as Response
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  vi.stubEnv('VITE_GRAPHQL_URL', '')
  vi.spyOn(AbortSignal, 'timeout').mockImplementation(() => new AbortController().signal)
  setContext('workspace-one', 'csrf-one')
})

afterEach(() => {
  setContext('', '')
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

describe('API request contracts', () => {
  it('returns a context copy and captures the workspace for in-flight REST and GraphQL requests', async () => {
    const copied = getContext()
    copied.project = 'changed-copy'
    copied.csrf = 'changed-copy'
    expect(getContext()).toEqual({ project: 'workspace-one', csrf: 'csrf-one' })

    let finishRest!: (result: Response) => void
    let finishGraphql!: (result: Response) => void
    fetchMock.mockReturnValueOnce(new Promise(resolve => { finishRest = resolve }))
      .mockReturnValueOnce(new Promise(resolve => { finishGraphql = resolve }))
    const restRequest = rest('/api/entries')
    const graphqlRequest = gql('{types{id}}')
    setContext('workspace-two', 'csrf-two')
    finishRest(response({ entries: [] }))
    finishGraphql(response({ data: { types: [] } }))

    await expect(restRequest).resolves.toEqual({ entries: [] })
    await expect(graphqlRequest).resolves.toEqual({ types: [] })
    for (const [, options] of fetchMock.mock.calls) {
      expect(options?.headers).toEqual({
        'X-Moss-Project': 'workspace-one',
        'X-Moss-CSRF': 'csrf-one',
        'Content-Type': 'application/json',
      })
      expect(options?.credentials).toBe('include')
      expect(options?.signal).toBeInstanceOf(AbortSignal)
    }
    expect(AbortSignal.timeout).toHaveBeenNthCalledWith(1, 30000)
    expect(AbortSignal.timeout).toHaveBeenNthCalledWith(2, 30000)

    fetchMock.mockResolvedValueOnce(response({ entries: [] }))
    await rest('/api/entries')
    expect(fetchMock.mock.calls[2][1]?.headers).toMatchObject({
      'X-Moss-Project': 'workspace-two', 'X-Moss-CSRF': 'csrf-two',
    })
  })

  it('sends the unchanged content-type mutation, variables, and explicit context to the configured GraphQL endpoint', async () => {
    const originalDocument = 'mutation($key:String!,$name:String!,$fields:JSON!,$version:Int,$migration:JSON){saveContentType(key:$key,name:$name,fields:$fields,version:$version,migration:$migration){id key name fields version entryCount}}'
    expect(saveContentTypeMutation).toBe(originalDocument)
    vi.stubEnv('VITE_GRAPHQL_URL', '/workspace/graphql')
    const variables = { key: 'article', name: 'Article', fields: [], version: null, migration: {} }
    fetchMock.mockResolvedValueOnce(response({ data: { saveContentType: { id: 'type-one' } } }))

    await expect(gql(saveContentTypeMutation, variables, { project: 'captured', csrf: 'captured-csrf' }))
      .resolves.toEqual({ saveContentType: { id: 'type-one' } })
    expect(fetchMock).toHaveBeenCalledWith('/workspace/graphql', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ query: originalDocument, variables }),
      headers: {
        'X-Moss-Project': 'captured', 'X-Moss-CSRF': 'captured-csrf', 'Content-Type': 'application/json',
      },
    }))
  })

  it('preserves multipart body identity and workspace headers while leaving the boundary to fetch', async () => {
    const body = new FormData()
    body.append('file', new Blob(['image']), 'image.png')
    fetchMock.mockResolvedValueOnce(response({ id: 'asset-one' }))

    await expect(rest('/api/assets', 'POST', body)).resolves.toEqual({ id: 'asset-one' })
    const [path, options] = fetchMock.mock.calls[0]
    expect(path).toBe('/api/assets')
    expect(options).toMatchObject({ method: 'POST', credentials: 'include' })
    expect(options?.body).toBe(body)
    expect(options?.headers).toEqual({ 'X-Moss-Project': 'workspace-one', 'X-Moss-CSRF': 'csrf-one' })
    expect(AbortSignal.timeout).toHaveBeenCalledWith(120000)
  })

  it('retains REST error codes and request IDs, with a readable fallback for structured details', async () => {
    fetchMock.mockResolvedValueOnce(response({ detail: 'Version conflict', code: 'CONFLICT' }, false, 'request-one'))
      .mockResolvedValueOnce(response({ detail: [{ loc: ['title'], msg: 'Required' }] }, false))

    await expect(rest('/api/entries', 'PATCH', { version: 1 })).rejects.toMatchObject({
      message: 'Version conflict', code: 'CONFLICT', requestId: 'request-one', uncertain: false,
    })
    await expect(rest('/api/entries')).rejects.toMatchObject({
      message: 'Request failed. Check the form values.', code: 'REQUEST_FAILED', requestId: undefined,
    })
  })

  it.each([
    { method: 'GET', error: new DOMException('Timed out', 'TimeoutError'), code: 'TIMEOUT', uncertain: false },
    { method: 'POST', error: new DOMException('Timed out', 'TimeoutError'), code: 'TIMEOUT', uncertain: true },
    { method: 'GET', error: new TypeError('Fetch failed'), code: 'NETWORK', uncertain: false },
    { method: 'PATCH', error: new TypeError('Fetch failed'), code: 'NETWORK', uncertain: true },
  ])('marks $code failures for $method with uncertain=$uncertain', async ({ method, error, code, uncertain }) => {
    fetchMock.mockRejectedValueOnce(error)
    await expect(rest('/api/entries', method)).rejects.toMatchObject({ code, uncertain })
  })

  it('retains structured GraphQL field paths, all messages, and first-error metadata', async () => {
    fetchMock.mockResolvedValueOnce(response({ errors: [
      { message: 'Title is required', extensions: {
        fieldPath: ['data', 'blocks', 2, 'title'], code: 'VALIDATION', requestId: 'request-two', reason: 'required',
      } },
      { message: 'Slug is reserved', extensions: { fieldPath: 'slug' } },
    ] }))

    await expect(gql('mutation{saveEntry{id}}')).rejects.toMatchObject({
      message: 'Title is required\nSlug is reserved',
      code: 'VALIDATION', requestId: 'request-two', reason: 'required', uncertain: false,
      fieldPath: 'data.blocks[2].title',
      fieldErrors: { 'data.blocks[2].title': 'Title is required', slug: 'Slug is reserved' },
    })
    expect(fetchMock.mock.calls[0][0]).toBe('/graphql')
  })

  it('uses legacy message paths when extensions omit them and leaves unrelated messages unassigned', async () => {
    fetchMock.mockResolvedValueOnce(response({ errors: [
      { message: 'Validation failed' },
      { message: 'data.blocks[2].title is required' },
      { message: 'slug already exists' },
    ] }))
    await expect(gql('mutation{saveEntry{id}}')).rejects.toMatchObject({
      fieldPath: 'data.blocks[2].title',
      fieldErrors: {
        'data.blocks[2].title': 'data.blocks[2].title is required', slug: 'slug already exists',
      },
    })

    fetchMock.mockResolvedValueOnce(response({ errors: [{ message: 'Permission denied' }] }))
    await expect(gql('{types{id}}')).rejects.toEqual(expect.objectContaining({
      message: 'Permission denied', code: 'REQUEST_FAILED', fieldPath: undefined, fieldErrors: undefined,
    }))
  })
})
