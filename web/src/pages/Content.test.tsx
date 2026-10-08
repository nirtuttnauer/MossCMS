import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { Content } from './Content'
import { gql, type Entry } from '../lib/api'
vi.mock('../lib/api', async importOriginal => ({ ...await importOriginal<typeof import('../lib/api')>(), gql: vi.fn() }))
afterEach(cleanup)
const types = [{id:'type', key:'article', name:'Articles', version:1, fields:[{name:'title', type:'text'}]}]
const entry: Entry = {id:'entry', typeKey:'article', slug:'live', title:'Live article', data:{title:'Live article'}, status:'scheduled', version:3, updatedAt:'2026-10-08T12:00:00Z', isLive:true, hasUnpublishedChanges:true, scheduledAt:'2027-01-01T12:00:00Z', scheduledRevision:2}
function setup(role='editor') {
  vi.mocked(gql).mockImplementation(async () => ({entries:{nodes:[entry],total:1,hasNextPage:false,endCursor:null},contentGroups:[{key:'article',name:'Articles',count:1}],assets:[]}))
  render(<Content types={types} role={role} onChanged={vi.fn()} />)
}
test('live editing defaults to draft and explains captured schedule', async () => {
  setup()
  fireEvent.click(await screen.findByRole('button',{name:'Edit'}))
  expect(screen.getByRole('button',{name:/^Save draft$/})).toBeTruthy()
  expect(screen.getByText(/Newer draft changes are not scheduled/)).toBeTruthy()
  fireEvent.click(screen.getByRole('button',{name:'Cancel schedule'}))
  await waitFor(() => expect(vi.mocked(gql).mock.calls.some(([query]) => query.includes('cancelSchedule'))).toBe(true))
})
test('readers can inspect publication state without action controls', async () => {
  setup('reader')
  fireEvent.click(await screen.findByRole('button',{name:'View'}))
  expect(screen.queryByRole('button',{name:'Cancel schedule'})).toBeNull()
  expect(screen.queryByRole('button',{name:'Unpublish'})).toBeNull()
  expect(screen.queryByRole('button',{name:/^Save draft$/})).toBeNull()
})
