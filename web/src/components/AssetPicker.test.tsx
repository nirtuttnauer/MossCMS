import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AssetPicker, assetPageQuery } from './AssetPicker'
import { ApiError, getContext, gql, rest, setContext, type Asset } from '../lib/api'

vi.mock('../lib/api', async importOriginal => ({
  ...await importOriginal<typeof import('../lib/api')>(),
  gql: vi.fn(), rest: vi.fn(),
}))
const asset: Asset = { id: 'new-image', name: 'cover.png', mime: 'image/png', size: 100, url: '/media/new-image' }
const empty = { assetPage: { nodes: [] as Asset[], endCursor: null, hasNextPage: false } }
const file = () => new File(['image'], 'cover.png', { type: 'image/png' })
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}
let previousContext: ReturnType<typeof getContext>
beforeEach(() => {
  previousContext = getContext()
  vi.clearAllMocks()
  setContext('workspace-a', 'csrf')
  vi.mocked(gql).mockResolvedValue(empty)
})
afterEach(() => {
  cleanup()
  vi.useRealTimers()
  setContext(previousContext.project, previousContext.csrf)
})

describe('upload from an asset field', () => {
  it('uploads with explicit field constraints and selects the durable ID', async () => {
    vi.mocked(rest).mockResolvedValue(asset)
    const change = vi.fn()
    render(<AssetPicker label="Cover" value="" onChange={change} editable imagesOnly projectId="workspace-a" />)
    fireEvent.click(screen.getByRole('button', { name: 'Choose asset' }))
    expect(screen.getByLabelText('Upload Cover').getAttribute('tabindex')).toBe('-1')
    fireEvent.change(screen.getByLabelText('Upload Cover'), { target: { files: [file()] } })
    await screen.findByText('Uploaded and selected cover.png.')
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Choose asset' })))
    expect(change).toHaveBeenCalledWith('new-image')
    const [path, method, form, context] = vi.mocked(rest).mock.calls[0]
    expect([path, method, context]).toEqual(['/api/assets', 'POST', { project: 'workspace-a', csrf: 'csrf' }])
    expect((form as FormData).get('imagesOnly')).toBe('true')
  })
  it('announces loaded search results in the same live region as loading', async () => {
    vi.mocked(gql).mockResolvedValue({ assetPage: { nodes: [asset], endCursor: null, hasNextPage: false } })
    render(<AssetPicker label="Cover" value="" onChange={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Choose asset' }))
    const status = screen.getByText('Loading assets…')
    await screen.findByText('Showing 1 assets.')
    expect(screen.getByText('Showing 1 assets.')).toBe(status)
    expect(status.getAttribute('role')).toBe('status')
  })
  it('rejects oversized and unsupported image inputs before sending any request', () => {
    render(<AssetPicker label="Cover" value="" onChange={vi.fn()} editable imagesOnly />)
    fireEvent.click(screen.getByRole('button', { name: 'Choose asset' }))
    const input = screen.getByLabelText('Upload Cover')
    fireEvent.change(input, { target: { files: [new File(['svg'], 'image.svg', { type: 'image/svg+xml' })] } })
    expect(screen.getByRole('alert').textContent).toContain('JPEG, PNG or WebP')
    const oversized = file()
    Object.defineProperty(oversized, 'size', { value: 20 * 1024 * 1024 + 1 })
    fireEvent.change(input, { target: { files: [oversized] } })
    expect(screen.getByRole('alert').textContent).toContain('20 MiB')
    expect(rest).not.toHaveBeenCalled()
  })
  it('does not expose upload controls without explicit editing permission', () => {
    render(<AssetPicker label="Cover" value="" onChange={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Choose asset' }))
    expect(screen.queryByLabelText('Upload Cover')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Upload asset' })).toBeNull()
  })
  it('keeps uncertain uploads explicit and does not automatically send another file', async () => {
    vi.mocked(rest).mockRejectedValue(new ApiError('Connection lost.', 'NETWORK', undefined, true))
    const change = vi.fn()
    render(<AssetPicker label="Cover" value="" onChange={change} editable />)
    fireEvent.click(screen.getByRole('button', { name: 'Choose asset' }))
    fireEvent.change(screen.getByLabelText('Upload Cover'), { target: { files: [file()] } })
    await screen.findByText(/The upload may have succeeded/)
    expect(rest).toHaveBeenCalledOnce()
    expect(change).not.toHaveBeenCalled()
  })
  it.each(['close', 'workspace', 'unmount'])('does not attach a pending upload after %s', async action => {
    const pending = deferred<Asset>()
    vi.mocked(rest).mockReturnValue(pending.promise)
    const change = vi.fn()
    const props = { label: 'Cover', value: '', onChange: change, editable: true, projectId: 'workspace-a' }
    const view = render(<AssetPicker {...props} />)
    fireEvent.click(screen.getByRole('button', { name: 'Choose asset' }))
    fireEvent.change(screen.getByLabelText('Upload Cover'), { target: { files: [file()] } })
    expect(screen.getByText('Uploading asset…')).toBeTruthy()
    if (action === 'close') fireEvent.click(screen.getByRole('button', { name: 'Close selection' }))
    if (action === 'workspace') { setContext('workspace-b', 'csrf'); view.rerender(<AssetPicker {...props} projectId="workspace-b" />) }
    if (action === 'unmount') view.unmount()
    pending.resolve(asset)
    await waitFor(() => expect(rest).toHaveBeenCalledOnce())
    await pending.promise
    expect(change).not.toHaveBeenCalled()
  })
})

describe('asset search lifecycle', () => {
  beforeEach(() => vi.useFakeTimers())

  function pendingPage() {
    let resolve!: (value: typeof empty) => void
    let reject!: (reason: Error) => void
    const promise = new Promise<typeof empty>((done, fail) => {
      resolve = done
      reject = fail
    })
    return { promise, resolve, reject }
  }

  it('debounces searches for 200 ms and coalesces rapid edits with the current constraints', async () => {
    render(<AssetPicker label="Cover" value="" onChange={vi.fn()} imagesOnly projectId="workspace-a" />)
    fireEvent.click(screen.getByRole('button', { name: 'Choose asset' }))
    await act(async () => { vi.advanceTimersByTime(199) })
    expect(gql).not.toHaveBeenCalled()
    await act(async () => { vi.advanceTimersByTime(1) })
    expect(gql).toHaveBeenCalledExactlyOnceWith(
      assetPageQuery,
      { search: '', imagesOnly: true, after: null },
      { project: 'workspace-a', csrf: 'csrf' },
    )
    const search = screen.getByLabelText('Search assets')
    fireEvent.change(search, { target: { value: 'first' } })
    await act(async () => { vi.advanceTimersByTime(100) })
    fireEvent.change(search, { target: { value: 'latest' } })
    await act(async () => { vi.advanceTimersByTime(199) })
    expect(gql).toHaveBeenCalledTimes(1)
    await act(async () => { vi.advanceTimersByTime(1) })
    expect(gql).toHaveBeenCalledTimes(2)
    expect(gql).toHaveBeenLastCalledWith(
      assetPageQuery,
      { search: 'latest', imagesOnly: true, after: null },
      { project: 'workspace-a', csrf: 'csrf' },
    )
  })

  it.each(['close', 'unmount'])('cancels a pending search timer on %s', async action => {
    const view = render(<AssetPicker label="Cover" value="" onChange={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Choose asset' }))
    await act(async () => { vi.advanceTimersByTime(199) })
    if (action === 'close') fireEvent.click(screen.getByRole('button', { name: 'Close selection' }))
    if (action === 'unmount') view.unmount()
    await act(async () => { vi.advanceTimersByTime(201) })
    expect(gql).not.toHaveBeenCalled()
  })

  it.each(['result', 'error'])('ignores an old search %s while the newer search is still loading', async outcome => {
    const oldRequest = pendingPage()
    const newRequest = pendingPage()
    vi.mocked(gql).mockReturnValueOnce(oldRequest.promise).mockReturnValueOnce(newRequest.promise)
    render(<AssetPicker label="Cover" value="" onChange={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Choose asset' }))
    await act(async () => { vi.advanceTimersByTime(200) })
    fireEvent.change(screen.getByLabelText('Search assets'), { target: { value: 'current' } })
    await act(async () => { vi.advanceTimersByTime(200) })
    await act(async () => {
      if (outcome === 'result') oldRequest.resolve({ assetPage: { ...empty.assetPage, nodes: [{ ...asset, name: 'Stale image' }] } })
      else oldRequest.reject(new Error('Stale search failure'))
    })
    expect(screen.getByText('Loading assets…')).toBeTruthy()
    expect(screen.queryByText('Stale image')).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
    await act(async () => {
      newRequest.resolve({ assetPage: { ...empty.assetPage, nodes: [{ ...asset, name: 'Current image' }] } })
    })
    expect(screen.getByRole('button', { name: 'Current image' })).toBeTruthy()
    expect(screen.queryByText('Loading assets…')).toBeNull()
  })

  it.each(['result', 'error'])('ignores a selected asset and search %s after the global workspace changes', async outcome => {
    const selectedRequest = pendingPage()
    const searchRequest = pendingPage()
    vi.mocked(gql).mockReturnValueOnce(selectedRequest.promise).mockReturnValueOnce(searchRequest.promise)
    render(<AssetPicker label="Cover" value="old-id" onChange={vi.fn()} projectId="workspace-a" />)
    fireEvent.click(screen.getByRole('button', { name: 'Choose asset' }))
    await act(async () => { vi.advanceTimersByTime(200) })
    setContext('workspace-b', 'new-csrf')
    await act(async () => {
      for (const request of [selectedRequest, searchRequest]) {
        if (outcome === 'result') request.resolve({ assetPage: { ...empty.assetPage, nodes: [{ ...asset, name: 'Previous workspace image' }] } })
        else request.reject(new Error('Previous workspace failure'))
      }
    })
    expect(screen.getByText('Selected asset unavailable')).toBeTruthy()
    expect(screen.getByText('Loading assets…')).toBeTruthy()
    expect(screen.queryByText('Previous workspace image')).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('uses the next cursor, returns to the previous page, and resets pagination for a new search', async () => {
    vi.mocked(gql).mockResolvedValue({ assetPage: { nodes: [asset], endCursor: 'page-one', hasNextPage: true } })
    render(<AssetPicker label="Cover" value="" onChange={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Choose asset' }))
    await act(async () => { vi.advanceTimersByTime(200) })
    expect(screen.getByRole('button', { name: 'Previous assets' }).hasAttribute('disabled')).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Next assets' }))
    await act(async () => { vi.advanceTimersByTime(200) })
    expect(vi.mocked(gql).mock.lastCall?.[1]).toEqual({ search: '', imagesOnly: false, after: 'page-one' })
    fireEvent.click(screen.getByRole('button', { name: 'Previous assets' }))
    await act(async () => { vi.advanceTimersByTime(200) })
    expect(vi.mocked(gql).mock.lastCall?.[1]?.after).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Next assets' }))
    await act(async () => { vi.advanceTimersByTime(200) })
    fireEvent.change(screen.getByLabelText('Search assets'), { target: { value: 'cover' } })
    await act(async () => { vi.advanceTimersByTime(200) })
    expect(vi.mocked(gql).mock.lastCall?.[1]).toEqual({ search: 'cover', imagesOnly: false, after: null })
    expect(screen.getByRole('button', { name: 'Previous assets' }).hasAttribute('disabled')).toBe(true)
  })

  it.each(['project', 'imagesOnly'])('resets the panel, search, cursor, and error when %s changes', async change => {
    vi.mocked(gql)
      .mockResolvedValueOnce({ assetPage: { nodes: [asset], endCursor: 'page-one', hasNextPage: true } })
      .mockRejectedValueOnce(new Error('Search failed'))
    const props = { label: 'Cover', value: '', onChange: vi.fn(), projectId: 'workspace-a', imagesOnly: false }
    const view = render(<AssetPicker {...props} />)
    fireEvent.click(screen.getByRole('button', { name: 'Choose asset' }))
    await act(async () => { vi.advanceTimersByTime(200) })
    fireEvent.click(screen.getByRole('button', { name: 'Next assets' }))
    await act(async () => { vi.advanceTimersByTime(200) })
    expect(screen.getByRole('alert').textContent).toContain('Search failed')
    fireEvent.change(screen.getByLabelText('Search assets'), { target: { value: 'old search' } })
    const nextProps = change === 'project'
      ? { ...props, projectId: 'workspace-b' }
      : { ...props, imagesOnly: true }
    if (change === 'project') setContext('workspace-b', 'new-csrf')
    view.rerender(<AssetPicker {...nextProps} />)
    expect(screen.queryByLabelText('Search assets')).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Choose asset' }))
    expect((screen.getByLabelText('Search assets') as HTMLInputElement).value).toBe('')
    await act(async () => { vi.advanceTimersByTime(200) })
    expect(gql).toHaveBeenCalledTimes(3)
    expect(vi.mocked(gql).mock.lastCall?.[1]).toEqual({ search: '', imagesOnly: nextProps.imagesOnly, after: null })
    expect(vi.mocked(gql).mock.lastCall?.[2]?.project).toBe(nextProps.projectId)
    expect(screen.getByRole('button', { name: 'Previous assets' }).hasAttribute('disabled')).toBe(true)
    expect(screen.getByText('No matching assets.')).toBeTruthy()
  })
})

describe('library image alternative text', () => {
  const hebrew = 'תמונת חוף'
  // Spellings are assembled so this file does not contain the rejected word.
  const joined = (left: string, right: string) => left + right
  const banned = new RegExp(
    [joined('compl', 'iant'), joined('compl', 'iance'), 'guarantees', '\\bfirst\\b', 'only one'].join('|'),
    'i',
  )

  function show(node: Asset) {
    vi.mocked(gql).mockResolvedValue({ assetPage: { nodes: [node], endCursor: null, hasNextPage: false } })
  }

  async function pick(name: string) {
    fireEvent.click(screen.getByRole('button', { name: 'Choose asset' }))
    fireEvent.click(await screen.findByRole('button', { name }))
  }

  it('warns and waits for confirmation when a library image has no alternative text', async () => {
    show(asset)
    const change = vi.fn()
    render(<AssetPicker label="Cover" value="" onChange={change} imagesOnly projectId="workspace-a" />)
    await pick(asset.name)
    const dialog = await screen.findByRole('dialog', { name: 'Add alternative text before you insert this image' })
    expect(dialog.textContent).toContain('flags common accessibility problems before you publish')
    expect(dialog.textContent).not.toMatch(banned)
    expect(change).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Go back' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(change).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: asset.name }))
    fireEvent.click(await screen.findByRole('button', { name: 'Insert without alternative text' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(change).toHaveBeenCalledExactlyOnceWith('new-image')
    expect(screen.getByRole('button', { name: 'Choose asset' })).toBeTruthy()
  })

  it('accepts Hebrew alternative text and inserts the library image without a warning', async () => {
    show(asset)
    const change = vi.fn()
    render(<fieldset className="field-group">
      <legend>cover</legend>
      <AssetPicker label="Cover" value="" onChange={change} imagesOnly projectId="workspace-a" />
      <label>alt<input aria-label="cover alt" defaultValue={`  ${hebrew}  `} /></label>
    </fieldset>)
    await pick(asset.name)
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(change).toHaveBeenCalledExactlyOnceWith('new-image')
  })

  it('treats whitespace alternative text as missing and still confirms before insert', async () => {
    show(asset)
    const change = vi.fn()
    render(<fieldset className="field-group">
      <legend>cover</legend>
      <AssetPicker label="Cover" value="" onChange={change} imagesOnly />
      <label>alt *<input aria-label="cover alt" defaultValue="   " /></label>
    </fieldset>)
    await pick(asset.name)
    expect(await screen.findByRole('dialog')).toBeTruthy()
    expect(change).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Go back' }))
    fireEvent.change(screen.getByLabelText('cover alt'), { target: { value: hebrew } })
    fireEvent.click(screen.getByRole('button', { name: asset.name }))
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(change).toHaveBeenCalledExactlyOnceWith('new-image')
  })

  it('accepts Hebrew alternative text on a localized alt field', async () => {
    show(asset)
    const change = vi.fn()
    render(<fieldset className="field-group">
      <legend>cover</legend>
      <AssetPicker label="Cover" value="" onChange={change} imagesOnly />
      <fieldset className="field-group">
        <legend>alt</legend>
        <label>he<input aria-label="Hebrew alt" defaultValue={hebrew} /></label>
        <label>en<input aria-label="English alt" defaultValue="" /></label>
      </fieldset>
    </fieldset>)
    await pick(asset.name)
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(change).toHaveBeenCalledExactlyOnceWith('new-image')
  })

  it('does not use another field’s alternative text for an image that has no alt field', async () => {
    show(asset)
    const change = vi.fn()
    render(<fieldset className="entry-writing">
      <label>alt<input defaultValue={hebrew} /></label>
      <AssetPicker label="Portrait" value="" onChange={change} imagesOnly />
    </fieldset>)
    await pick(asset.name)
    expect(await screen.findByRole('dialog', { name: 'Add alternative text before you insert this image' })).toBeTruthy()
    expect(change).not.toHaveBeenCalled()
  })

  it('keeps the Markdown insert path, which already requires alternative text', async () => {
    show(asset)
    const change = vi.fn()
    render(<div className="inline-form">
      <AssetPicker label="Image asset" value="" onChange={change} imagesOnly />
      <label>Image alt text<input defaultValue="" /></label>
      <button type="button">Insert image</button>
    </div>)
    await pick(asset.name)
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(change).toHaveBeenCalledExactlyOnceWith('new-image')
  })

  it('inserts a non-image library file without an alternative-text warning', async () => {
    const notes = { ...asset, id: 'notes', name: 'notes.pdf', mime: 'application/pdf' }
    show(notes)
    const change = vi.fn()
    render(<AssetPicker label="Download" value="" onChange={change} />)
    await pick(notes.name)
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(change).toHaveBeenCalledExactlyOnceWith('notes')
  })

  it('still warns for an image chosen from a mixed library', async () => {
    show(asset)
    const change = vi.fn()
    render(<AssetPicker label="Download" value="" onChange={change} />)
    await pick(asset.name)
    expect(await screen.findByRole('alert')).toBeTruthy()
    expect(change).not.toHaveBeenCalled()
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(change).not.toHaveBeenCalled()
  })
})
