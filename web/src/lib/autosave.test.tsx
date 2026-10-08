import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
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
