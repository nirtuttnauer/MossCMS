import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { useDraftAutosave } from './autosave'
import { ApiError, gql, setContext, type Entry } from './api'
vi.mock('./api', async original => ({...await original<typeof import('./api')>(),gql:vi.fn()}))
afterEach(() => {cleanup();vi.restoreAllMocks();vi.mocked(gql).mockReset()})
const initial:Entry={id:'one',typeKey:'article',slug:'hello',title:'Hello',data:{title:'Hello'},status:'draft',version:1,updatedAt:'2026-10-08T00:00:00Z',isLive:false,hasUnpublishedChanges:true}
const values={typeKey:'article',slug:'hello',data:{title:'Hello'}}
test('serializes changes made during an in-flight save and uses acknowledged version', async () => {
  setContext('first','csrf')
  let release!: (value:unknown)=>void
  vi.mocked(gql).mockImplementationOnce(() => new Promise(resolve=>{release=resolve})).mockResolvedValueOnce({saveDraft:{...initial,version:3,data:{title:'Third'}}})
  const hook=renderHook(({data})=>useDraftAutosave(initial,{...values,data},true,true,10),{initialProps:{data:values.data}})
  hook.rerender({data:{title:'Second'}})
  await waitFor(()=>expect(gql).toHaveBeenCalledTimes(1))
  hook.rerender({data:{title:'Third'}})
  await act(async()=>{release({saveDraft:{...initial,version:2,data:{title:'Second'}}})})
  await waitFor(()=>expect(hook.result.current.state).toBe('Saved'))
  expect(vi.mocked(gql).mock.calls[1][1]?.version).toBe(2)
  expect(hook.result.current.entry?.data.title).toBe('Third')
})
test('cancels delayed writes after workspace changes',async()=>{
  setContext('first','csrf')
  const hook=renderHook(({data})=>useDraftAutosave(initial,{...values,data},true,true,10),{initialProps:{data:values.data}})
  hook.rerender({data:{title:'Second'}})
  setContext('second','other-csrf')
  await act(async()=>{await new Promise(resolve=>setTimeout(resolve,30))})
  expect(gql).not.toHaveBeenCalled()
})
test('conflicts preserve local edits and expose comparison rather than retrying',async()=>{
  setContext('first','csrf')
  vi.mocked(gql).mockRejectedValueOnce(new ApiError('Newer server version','CONFLICT'))
  const hook=renderHook(({data})=>useDraftAutosave(initial,{...values,data},true,true,10),{initialProps:{data:values.data}})
  hook.rerender({data:{title:'Local edit'}})
  await waitFor(()=>expect(hook.result.current.state).toBe('Conflict'))
  expect(hook.result.current.dirty).toBe(true)
  expect(hook.result.current.entry?.version).toBe(1)
  expect(gql).toHaveBeenCalledTimes(1)
})
test('lost save response is reconciled by receipt without a second create',async()=>{
  setContext('first','csrf')
  vi.mocked(gql).mockRejectedValueOnce(new ApiError('Timed out','TIMEOUT',undefined,true)).mockResolvedValueOnce({draftReceipt:{...initial,version:2,data:{title:'Saved'}}})
  const hook=renderHook(({data})=>useDraftAutosave(null,{...values,data},true,true,10),{initialProps:{data:values.data}})
  hook.rerender({data:{title:'Saved'}})
  await waitFor(()=>expect(hook.result.current.entry?.version).toBe(2))
  expect(vi.mocked(gql).mock.calls[0][0]).toContain('saveDraft')
  expect(vi.mocked(gql).mock.calls[1][0]).toContain('draftReceipt')
  expect(vi.mocked(gql).mock.calls[1][1]?.key).toBe(vi.mocked(gql).mock.calls[0][1]?.requestKey)
  expect(gql).toHaveBeenCalledTimes(2)
})

test('field-level slug collisions remain correctable instead of blocking as concurrent edits', async () => {
  setContext('first', 'csrf')
  vi.mocked(gql).mockRejectedValueOnce(new ApiError('Slug reserved', 'CONFLICT', undefined, false, 'slug', { slug: 'Slug reserved' }, 'slug_conflict'))
    .mockResolvedValueOnce({ saveDraft: { ...initial, slug: 'unique', version: 2 } })
  const hook = renderHook(({ slug }) => useDraftAutosave(initial, { ...values, slug }, true, true, 10), { initialProps: { slug: initial.slug } })
  hook.rerender({ slug: 'taken' })
  await waitFor(() => expect(hook.result.current.state).toBe('Error'))
  expect(hook.result.current.validationErrors).toEqual({ slug: 'Slug reserved' })
  hook.rerender({ slug: 'unique' })
  await act(async () => { await hook.result.current.flush() })
  expect(hook.result.current.entry?.slug).toBe('unique')
  expect(hook.result.current.state).toBe('Saved')
})

test('restoring a required zero to the identical saved baseline clears Incomplete without a write', async () => {
  setContext('first', 'csrf')
  const savedEntry = { ...initial, version: 4, data: { title: 'Hello', details: { score: 0 } } }
  const hook = renderHook(({ score }: { score: number | null }) => useDraftAutosave(
    savedEntry, { ...values, data: { title: 'Hello', details: { score } } }, true, score !== null, 10,
  ), { initialProps: { score: 0 as number | null } })
  hook.rerender({ score: null })
  expect(hook.result.current.state).toBe('Incomplete')
  expect(hook.result.current.dirty).toBe(true)
  hook.rerender({ score: 0 })
  await waitFor(() => expect(hook.result.current.state).toBe('Saved'))
  expect(hook.result.current.dirty).toBe(false)
  await act(async () => { await hook.result.current.flush() })
  expect(hook.result.current.entry).toBe(savedEntry)
  expect(hook.result.current.entry?.version).toBe(4)
  expect(gql).not.toHaveBeenCalled()
})

describe('autosave request lifecycle', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    setContext('first', 'csrf')
  })
  afterEach(() => {
    cleanup()
    vi.useRealTimers()
  })

  test('debounces edits for the default delay and saves only the latest snapshot', async () => {
    vi.mocked(gql).mockResolvedValue({ saveDraft: { ...initial, version: 2, data: { title: 'Latest' } } })
    const hook = renderHook(({ data }) => useDraftAutosave(initial, { ...values, data }, true, true), {
      initialProps: { data: values.data },
    })
    hook.rerender({ data: { title: 'First edit' } })
    await act(async () => { await vi.advanceTimersByTimeAsync(899) })
    expect(gql).not.toHaveBeenCalled()
    hook.rerender({ data: { title: 'Latest' } })
    await act(async () => { await vi.advanceTimersByTimeAsync(899) })
    expect(gql).not.toHaveBeenCalled()
    await act(async () => { await vi.advanceTimersByTimeAsync(1) })
    expect(gql).toHaveBeenCalledTimes(1)
    expect(vi.mocked(gql).mock.calls[0][1]).toEqual({
      ...values,
      data: { title: 'Latest' },
      id: initial.id,
      version: initial.version,
      requestKey: expect.any(String),
    })
    expect(vi.mocked(gql).mock.calls[0][2]).toEqual({ project: 'first', csrf: 'csrf' })
    expect(hook.result.current.state).toBe('Saved')
  })

  test.each(['disable', 'unmount'])('cancels the pending timer on %s', async action => {
    const hook = renderHook(({ data, enabled }) => useDraftAutosave(initial, { ...values, data }, enabled, true, 10), {
      initialProps: { data: values.data, enabled: true },
    })
    hook.rerender({ data: { title: 'Pending' }, enabled: true })
    await act(async () => { await vi.advanceTimersByTimeAsync(9) })
    if (action === 'disable') {
      hook.rerender({ data: { title: 'Pending' }, enabled: false })
    } else {
      hook.unmount()
    }
    await act(async () => { await vi.advanceTimersByTimeAsync(20) })
    expect(gql).not.toHaveBeenCalled()
  })

  test.each([
    { online: false, valid: true, state: 'Offline', error: 'Offline. Your edits remain in this editor.' },
    { online: true, valid: false, state: 'Incomplete', error: 'Complete the required fields and slug before saving.' },
  ])('keeps $state edits local during delayed and explicit saves', async ({ online, valid, state, error }) => {
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(online)
    const hook = renderHook(({ data }) => useDraftAutosave(initial, { ...values, data }, true, valid, 10), {
      initialProps: { data: values.data },
    })
    hook.rerender({ data: { title: 'Local' } })
    await act(async () => { await vi.advanceTimersByTimeAsync(20) })
    expect(hook.result.current.state).toBe(state)
    await act(async () => { await expect(hook.result.current.flush()).rejects.toThrow(error) })
    expect(gql).not.toHaveBeenCalled()
    expect(hook.result.current.dirty).toBe(true)
    expect(hook.result.current.entry).toEqual(initial)
  })

  test.each(['missing', 'failed'])('retries the identical request after a %s receipt', async receipt => {
    vi.mocked(gql).mockRejectedValueOnce(new ApiError('Timed out', 'TIMEOUT', undefined, true))
    if (receipt === 'missing') {
      vi.mocked(gql).mockResolvedValueOnce({ draftReceipt: null })
    } else {
      vi.mocked(gql).mockRejectedValueOnce(new Error('Receipt unavailable'))
    }
    vi.mocked(gql).mockResolvedValueOnce({ saveDraft: { ...initial, version: 2, data: { title: 'Pending' } } })
    const hook = renderHook(({ data }) => useDraftAutosave(initial, { ...values, data }, true, true, 10), {
      initialProps: { data: values.data },
    })
    hook.rerender({ data: { title: 'Pending' } })
    await act(async () => { await vi.advanceTimersByTimeAsync(10) })
    expect(hook.result.current.state).toBe('Uncertain')
    expect(hook.result.current.dirty).toBe(true)
    expect(vi.mocked(gql).mock.calls[1][1]).toEqual({ key: vi.mocked(gql).mock.calls[0][1]?.requestKey })
    await act(async () => { await vi.advanceTimersByTimeAsync(1000) })
    expect(gql).toHaveBeenCalledTimes(2)
    await act(async () => { hook.result.current.retry() })
    expect(gql).toHaveBeenCalledTimes(3)
    expect(vi.mocked(gql).mock.calls[2]).toEqual(vi.mocked(gql).mock.calls[0])
    expect(hook.result.current.state).toBe('Saved')
    expect(hook.result.current.dirty).toBe(false)
  })

  test('blocks explicit saves and subsequent edits after a concurrent conflict', async () => {
    vi.mocked(gql).mockRejectedValueOnce(new ApiError('Newer server version', 'CONFLICT'))
    const hook = renderHook(({ data }) => useDraftAutosave(initial, { ...values, data }, true, true, 10), {
      initialProps: { data: values.data },
    })
    hook.rerender({ data: { title: 'Local' } })
    await act(async () => { await vi.advanceTimersByTimeAsync(10) })
    hook.rerender({ data: { title: 'Another local edit' } })
    await act(async () => { await vi.advanceTimersByTimeAsync(20) })
    await act(async () => {
      await expect(hook.result.current.flush()).rejects.toThrow('Resolve the concurrent edit conflict before saving.')
    })
    expect(gql).toHaveBeenCalledTimes(1)
    expect(hook.result.current.state).toBe('Conflict')
    expect(hook.result.current.dirty).toBe(true)
  })

  test('does not send queued edits when an in-flight save completes after unmount', async () => {
    let release!: (value: unknown) => void
    vi.mocked(gql).mockImplementationOnce(() => new Promise(resolve => { release = resolve }))
    const hook = renderHook(({ data }) => useDraftAutosave(initial, { ...values, data }, true, true, 10), {
      initialProps: { data: values.data },
    })
    hook.rerender({ data: { title: 'Saving' } })
    let outcome!: Promise<Entry | null | string>
    act(() => { outcome = hook.result.current.flush().catch(reason => reason.message) })
    hook.rerender({ data: { title: 'Queued' } })
    hook.unmount()
    await act(async () => { release({ saveDraft: { ...initial, version: 2, data: { title: 'Saving' } } }) })
    expect(await outcome).toBe('Editor workspace changed; delayed save cancelled.')
    await act(async () => { await vi.advanceTimersByTimeAsync(20) })
    expect(gql).toHaveBeenCalledTimes(1)
  })
})
