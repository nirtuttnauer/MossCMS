import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { Content } from './Content'
import { gql, type Entry } from '../lib/api'
vi.mock('../lib/api', async importOriginal => ({ ...await importOriginal<typeof import('../lib/api')>(), gql: vi.fn() }))
afterEach(() => {
  cleanup()
  location.hash = ''
  history.replaceState(null, '', '/')
})
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

test('lost publication response remains checkable without blind repeated publish',async()=>{
  const {EntryEditor}=await import('./EntryEditor')
  const {ApiError}=await import('../lib/api')
  const saved=vi.fn()
  vi.mocked(gql).mockImplementation(async(query)=>{
    if(query.includes('saveEntry('))throw new ApiError('Lost response','NETWORK',undefined,true)
    if(query.includes('draftReceipt('))return {draftReceipt:null}
    return {entries:{nodes:[]},assets:[]}
  })
  render(<EntryEditor entry={entry} initialType="article" types={types} editable onClose={vi.fn()} onSaved={saved} />)
  fireEvent.click(screen.getByRole('button',{name:/^Immediate publication/}))
  fireEvent.submit(screen.getByRole('button',{name:'Publish now'}).closest('form')!)
  await screen.findByText(/Publication outcome is unconfirmed/)
  expect(saved).not.toHaveBeenCalled()
  fireEvent.click(screen.getAllByRole('button',{name:'Check outcome'})[0])
  await waitFor(()=>expect(vi.mocked(gql).mock.calls.filter(([query])=>query.includes('draftReceipt(')).length).toBe(2))
  expect(vi.mocked(gql).mock.calls.filter(([query])=>query.includes('saveEntry(')).length).toBe(1)
})

test('partial bulk trash reports counts, retains selection of unresolved entries and allows retry', async () => {
  const { ApiError } = await import('../lib/api')
  const entries: Entry[] = [
    { id: 'e1', typeKey: 'article', slug: 'e1', title: 'Entry 1', data: {}, status: 'draft', version: 1, updatedAt: '2026-10-08T12:00:00Z', isLive: false, hasUnpublishedChanges: false },
    { id: 'e2', typeKey: 'article', slug: 'e2', title: 'Entry 2', data: {}, status: 'draft', version: 1, updatedAt: '2026-10-08T12:00:00Z', isLive: false, hasUnpublishedChanges: false },
    { id: 'e3', typeKey: 'article', slug: 'e3', title: 'Entry 3', data: {}, status: 'published', version: 2, updatedAt: '2026-10-08T12:00:00Z', isLive: true, hasUnpublishedChanges: false },
    { id: 'e4', typeKey: 'article', slug: 'e4', title: 'Entry 4', data: {}, status: 'draft', version: 1, updatedAt: '2026-10-08T12:00:00Z', isLive: false, hasUnpublishedChanges: false },
    { id: 'e5', typeKey: 'article', slug: 'e5', title: 'Entry 5', data: {}, status: 'draft', version: 1, updatedAt: '2026-10-08T12:00:00Z', isLive: false, hasUnpublishedChanges: false },
  ]
  vi.mocked(gql).mockImplementation(async (query, vars: any) => {
    if (query.includes('entries(')) {
      return { entries: { nodes: entries, total: 5, hasNextPage: false, endCursor: null }, contentGroups: [{ key: 'article', name: 'Articles', count: 5 }] }
    }
    if (query.includes('deleteEntry(')) {
      if (vars?.id === 'e3') throw new ApiError('Conflict trashing item', 'CONFLICT')
      return { deleteEntry: true }
    }
    if (query.includes('entry(')) {
      return { entry: { ...entries.find(e => e.id === vars?.id), version: 3, status: 'published' } }
    }
    return {}
  })

  render(<Content types={types} role="editor" onChanged={vi.fn()} />)
  const selectAll = await screen.findByLabelText('Select all entries')
  fireEvent.click(selectAll)
  const trashBtn = screen.getByRole('button', { name: 'Trash 5' })
  fireEvent.click(trashBtn)

  expect(screen.getByText(/Moving live or scheduled content to trash unpublishes it immediately/)).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Trash' })).toBeTruthy()

  fireEvent.click(screen.getByRole('button', { name: 'Move to trash' }))

  await screen.findByText('2 completed, 1 failed, 2 not attempted')
  expect(screen.getByText(/Entry 3: Conflict trashing item/)).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Retry unresolved entries' })).toBeTruthy()
})

test('lost response reconciles current status before reporting success or retrying', async () => {
  const { ApiError } = await import('../lib/api')
  const entryLost: Entry = { id: 'elost', typeKey: 'article', slug: 'elost', title: 'Lost entry', data: {}, status: 'draft', version: 1, updatedAt: '2026-10-08T12:00:00Z', isLive: false, hasUnpublishedChanges: false }
  let deleteAttempts = 0
  vi.mocked(gql).mockImplementation(async (query, vars: any) => {
    if (query.includes('entries(')) {
      return { entries: { nodes: [entryLost], total: 1, hasNextPage: false, endCursor: null }, contentGroups: [{ key: 'article', name: 'Articles', count: 1 }] }
    }
    if (query.includes('deleteEntry(')) {
      deleteAttempts++
      throw new ApiError('Lost response', 'NETWORK', undefined, true)
    }
    if (query.includes('entry(')) {
      return { entry: { ...entryLost, status: 'deleted' } }
    }
    return {}
  })

  render(<Content types={types} role="editor" onChanged={vi.fn()} />)
  const selectAll = await screen.findByLabelText('Select all entries')
  fireEvent.click(selectAll)
  fireEvent.click(screen.getByRole('button', { name: 'Trash 1' }))
  fireEvent.click(screen.getByRole('button', { name: 'Move to trash' }))

  await waitFor(() => expect(screen.getByText(/1 entry moved to trash/)).toBeTruthy())
  expect(deleteAttempts).toBe(1)
})

test('validation errors appear beside fields and in error summary with focus jumping and clear-on-type', async () => {
  const { EntryEditor } = await import('./EntryEditor')
  vi.mocked(gql).mockImplementation(async () => ({ entries: { nodes: [] }, assets: [] }))
  const newEntry: Entry = {
    id: 'e-val',
    typeKey: 'post',
    slug: '',
    title: '',
    data: { title: null, author: null },
    status: 'draft',
    version: 1,
    updatedAt: '2026-10-08T12:00:00Z',
    isLive: false,
    hasUnpublishedChanges: false
  }
  const postTypes = [{
    id: 'type-post',
    key: 'post',
    name: 'Posts',
    version: 1,
    fields: [
      { name: 'title', type: 'text', required: true },
      { name: 'author', type: 'text', required: true }
    ]
  }]
  render(<EntryEditor entry={newEntry} initialType="post" types={postTypes} editable onClose={vi.fn()} onSaved={vi.fn()} />)

  const form = screen.getByRole('button', { name: /^Save draft$/ }).closest('form')!
  fireEvent.submit(form)

  expect(screen.getByRole('alert', { name: /Please fix the following errors/ })).toBeTruthy()
  expect(screen.getAllByText('Slug is required.').length).toBe(2)
  expect(screen.getAllByText('title is required.').length).toBe(2)
  expect(screen.getAllByText('author is required.').length).toBe(2)

  const slugInput = screen.getByLabelText(/^Slug/)
  expect(document.activeElement).toBe(slugInput)

  const titleLink = screen.getByRole('link', { name: 'title is required.' })
  fireEvent.click(titleLink)
  const titleInput = screen.getByLabelText(/^title \*/)
  expect(document.activeElement).toBe(titleInput)

  fireEvent.change(titleInput, { target: { value: 'My Post Title' } })
  expect(screen.queryByText('title is required.')).toBeNull()
  expect(screen.getAllByText('author is required.').length).toBe(2)
})

test('server field errors populate inline field errors and error summary', async () => {
  const { EntryEditor } = await import('./EntryEditor')
  const { ApiError } = await import('../lib/api')
  const entryItem: Entry = {
    id: 'e-srv',
    typeKey: 'post',
    slug: 'post-1',
    title: 'Post 1',
    data: { title: 'Post 1', author: 'Alice' },
    status: 'draft',
    version: 1,
    updatedAt: '2026-10-08T12:00:00Z',
    isLive: false,
    hasUnpublishedChanges: false
  }
  const postTypes = [{
    id: 'type-post',
    key: 'post',
    name: 'Posts',
    version: 1,
    fields: [
      { name: 'title', type: 'text', required: true },
      { name: 'author', type: 'text', required: true }
    ]
  }]

  vi.mocked(gql).mockImplementation(async (query) => {
    if (query.includes('saveDraft(') || query.includes('saveEntry(')) {
      throw new ApiError('Slug already in use', 'CONFLICT', undefined, false, 'slug', { slug: 'Slug already in use' })
    }
    return { entries: { nodes: [] }, assets: [] }
  })

  render(<EntryEditor entry={entryItem} initialType="post" types={postTypes} editable onClose={vi.fn()} onSaved={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: /^Immediate publication/ }))
  const form = screen.getByRole('button', { name: /^Publish now$/ }).closest('form')!
  fireEvent.submit(form)

  await screen.findByRole('alert', { name: /Please fix the following errors/ })
  expect(screen.getAllByText('Slug already in use').length).toBe(2)
  const slugInput = screen.getByLabelText(/^Slug/)
  await waitFor(() => expect(document.activeElement).toBe(slugInput))
})


test('duplicating an entry deep-copies data, proposes copy title and slug, and creates no record until explicitly saved', async () => {
  const complexEntry: Entry = {
    id: 'entry-orig',
    typeKey: 'article',
    slug: 'orig-slug',
    title: 'Original Post',
    data: {
      title: 'Original Post',
      nested: { tags: ['tech', 'cms'], count: 5 },
      localized: { en: 'Hello', fr: 'Bonjour' },
    },
    status: 'scheduled',
    version: 4,
    updatedAt: '2026-10-08T12:00:00Z',
    isLive: true,
    hasUnpublishedChanges: true,
    scheduledAt: '2027-01-01T12:00:00Z',
    scheduledRevision: 3,
  }

  const complexTypes = [{
    id: 'type-art',
    key: 'article',
    name: 'Articles',
    version: 1,
    fields: [
      { name: 'title', type: 'text' },
      { name: 'nested', type: 'object' },
      { name: 'localized', type: 'text', localized: true },
    ],
  }]

  vi.mocked(gql).mockReset()
  vi.mocked(gql).mockImplementation(async (query) => {
    if (query.includes('entries(')) {
      return {
        entries: { nodes: [complexEntry], total: 1, hasNextPage: false, endCursor: null },
        contentGroups: [{ key: 'article', name: 'Articles', count: 1 }],
      }
    }
    if (query.includes('saveDraft(') || query.includes('saveEntry(')) {
      return { saveDraft: { ...complexEntry, id: 'entry-copy-new', version: 1, status: 'draft' } }
    }
    return { entries: { nodes: [] }, assets: [] }
  })

  render(<Content types={complexTypes} role="editor" onChanged={vi.fn()} />)

  // Duplicate button in row actions
  const dupBtn = await screen.findByRole('button', { name: 'Duplicate' })
  expect(dupBtn).toBeDefined()

  // Initial mutation count before clicking duplicate
  const callsBefore = vi.mocked(gql).mock.calls.filter(([q]) => q.includes('saveEntry') || q.includes('saveDraft')).length
  expect(callsBefore).toBe(0)

  fireEvent.click(dupBtn)

  // Duplication banner is shown
  await screen.findByText(/Duplicating from/)
  expect(screen.getByText(/Duplicating from/)).toBeDefined()
  expect(screen.getAllByText(/Original Post/).length).toBeGreaterThan(0)
  expect(screen.getByText(/Version 4/)).toBeDefined()
  expect(screen.getByText(/This draft is not saved until you click Save draft/)).toBeDefined()

  // Proposes copy slug and copy title
  const slugInput = screen.getByLabelText(/^Slug/) as HTMLInputElement
  expect(slugInput.value).toMatch(/^orig-slug-copy-[a-f0-9]{8}$/)
  expect(screen.getByText('Original Post (Copy)')).toBeDefined()

  // No record is created on the backend yet
  const callsAfterOpen = vi.mocked(gql).mock.calls.filter(([q]) => q.includes('saveEntry') || q.includes('saveDraft')).length
  expect(callsAfterOpen).toBe(0)

  // Status defaults to draft, not scheduled/live
  expect(screen.queryByText(/Scheduled revision/)).toBeNull()

  // Click Save draft explicitly
  const saveBtn = screen.getByRole('button', { name: /^Save draft$/ })
  fireEvent.submit(saveBtn.closest('form')!)

  // Form submit saves the new copy
  await waitFor(() => {
    const saveCall = vi.mocked(gql).mock.calls.find(([q]) => q.includes('saveDraft') || q.includes('saveEntry'))
    expect(saveCall).toBeDefined()
    const vars = saveCall![1] as any
    expect(vars.slug).toBe(slugInput.value)
    expect(vars.data.title).toBe('Original Post (Copy)')
    expect(vars.data.nested).toEqual({ tags: ['tech', 'cms'], count: 5 })
    expect(vars.data.localized).toEqual({ en: 'Hello', fr: 'Bonjour' })
      })
})

test('readers cannot duplicate entries and duplicate button is not shown in list', async () => {
  setup('reader')
  await screen.findByRole('button', { name: 'View' })
  expect(screen.queryByRole('button', { name: 'Duplicate' })).toBeNull()
})

test('duplicate save loss reconciles and explicit retry retains the same request key', async () => {
  const { EntryEditor } = await import('./EntryEditor')
  const { ApiError } = await import('../lib/api')
  const source = { ...entry, status: 'published', scheduledAt: '2027-01-01T10:00:00Z' }
  const seed = { id: source.id, version: source.version, typeKey: source.typeKey, title: source.title, slug: `${source.slug}-copy`, data: { title: `${source.title} (Copy)` } }
  let writes = 0
  vi.mocked(gql).mockReset()
  vi.mocked(gql).mockImplementation(async query => {
    if (query.includes('saveDraft(')) { writes++; if (writes === 1) throw new ApiError('Lost', 'NETWORK', undefined, true); return { saveDraft: { ...source, id: 'copy-new', slug: seed.slug, data: seed.data, version: 1, status: 'draft', isLive: false, scheduledAt: null } } }
    if (query.includes('draftReceipt(')) return { draftReceipt: null }
    return { entries: { nodes: [] }, assets: [] }
  })
  const saved = vi.fn()
  render(<EntryEditor entry={null} seed={seed} initialType="article" types={types} editable onClose={vi.fn()} onSaved={saved} />)
  expect(screen.queryByRole('button', { name: /^Publish now/ })).toBeNull()
  fireEvent.submit(screen.getByRole('button', { name: 'Save draft' }).closest('form')!)
  await screen.findByText(/Save outcome is unconfirmed/)
  expect(saved).not.toHaveBeenCalled()
  fireEvent.submit(screen.getByRole('button', { name: 'Save draft' }).closest('form')!)
  await waitFor(() => expect(saved).toHaveBeenCalled())
  const mutations = vi.mocked(gql).mock.calls.filter(([query]) => query.includes('saveDraft('))
  expect(mutations.length).toBe(2)
  expect(mutations[0][1]?.requestKey).toBe(mutations[1][1]?.requestKey)
  expect(mutations[0][1]?.id).toBeUndefined()
  expect(mutations[0][1]).not.toHaveProperty('scheduledAt')
})

test('publishing URL impact follows homepage canonical paths', async () => {
  const { EntryEditor } = await import('./EntryEditor')
  vi.mocked(gql).mockImplementation(async () => ({ entries: { nodes: [] }, assets: [] }))
  const pageType = { id: 'pages', key: 'sitePage', name: 'Pages', version: 1, fields: [{ name: 'title', type: 'text' }, { name: 'kind', type: 'text' }] }
  const home = { ...entry, typeKey: 'sitePage', slug: 'home', data: { title: 'Home', kind: 'home' }, publishedSlug: 'home', publishedData: { title: 'Home', kind: 'home' } }
  render(<EntryEditor entry={home} types={[pageType]} initialType="sitePage" editable onSaved={vi.fn()} onClose={vi.fn()} />)
  fireEvent.change(screen.getByLabelText(/^Slug/), { target: { value: 'welcome' } })
  fireEvent.click(screen.getByRole('button', { name: /^Immediate publication/ }))
  expect(screen.queryByText(/Publishing changes the public URL/)).toBeNull()
  fireEvent.change(screen.getByLabelText('kind'), { target: { value: 'page' } })
  expect(screen.getByText(/Publishing changes the public URL/).textContent).toContain('from / to /welcome')
})

test.each(['partial', 'complete'])('recovers bulk-trash keyboard focus after a %s result disables its action', async result => {
  const { ApiError, setContext } = await import('../lib/api')
  setContext('focus-workspace', 'csrf')
  const entries = [1, 2, 3].map(index => ({ ...entry, id: `focus-${index}`, title: `Focus entry ${index}`, status: 'draft', isLive: false, scheduledAt: null }))
  const removed = new Set<string>()
  let finish!: (value: { deleteEntry: boolean }) => void, fail!: (reason: Error) => void
  const lastDelete = new Promise<{ deleteEntry: boolean }>((resolve, reject) => { finish = resolve; fail = reject })
  vi.mocked(gql).mockImplementation(async (query, variables) => {
    if (query.includes('deleteEntry(')) {
      if (variables?.id === 'focus-3') {
        const response = await lastDelete
        removed.add('focus-3')
        return response
      }
      removed.add(String(variables?.id))
      return { deleteEntry: true }
    }
    if (query.includes('entry(')) return { entry: entries.find(item => item.id === variables?.id) }
    const visible = entries.filter(item => !removed.has(item.id))
    return { entries: { nodes: visible, total: visible.length, endCursor: null, hasNextPage: false }, contentGroups: [{ key: 'article', name: 'Articles', count: visible.length }] }
  })
  render(<Content types={types} role="editor" onChanged={vi.fn()} />)
  await screen.findByText('Focus entry 1')
  fireEvent.click(screen.getByLabelText('Select all entries'))
  const opener = screen.getByRole('button', { name: 'Trash 3' })
  opener.focus()
  fireEvent.click(opener)
  const action = await screen.findByRole('button', { name: 'Move to trash' })
  action.focus()
  fireEvent.click(action)
  await waitFor(() => expect((action as HTMLButtonElement).disabled).toBe(true))
  action.blur() // Reproduce Safari losing focus when the focused action becomes disabled.
  if (result === 'partial') fail(new ApiError('Concurrent edit', 'CONFLICT'))
  else finish({ deleteEntry: true })
  if (result === 'partial') {
    const retry = await screen.findByRole('button', { name: 'Retry unresolved entries' })
    await waitFor(() => expect(document.activeElement).toBe(retry))
    expect((retry as HTMLButtonElement).disabled).toBe(false)
    expect(screen.getByText('2 completed, 1 failed, 0 not attempted')).toBeTruthy()
  } else {
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('heading', { name: 'Content', level: 1 })))
    expect(opener.isConnected).toBe(false)
  }
})


test('a delayed search preserves navigation to another workspace before the old content unmounts', async () => {
  history.replaceState(null, '', '/#content?workspace=a&type=article')
  vi.mocked(gql).mockResolvedValue({ entries: { nodes: [entry], total: 1, hasNextPage: false, endCursor: null }, contentGroups: [] })
  render(<Content projectId="a" types={types} role="editor" onChanged={vi.fn()} />)
  await screen.findByRole('button', { name: 'Edit' })
  fireEvent.change(screen.getByLabelText('Search entries'), { target: { value: 'pending search' } })
  const destination = '#content?workspace=b&type=beta'
  history.replaceState(null, '', destination)
  fireEvent(window, new Event('hashchange'))
  await waitFor(() => expect(vi.mocked(gql).mock.calls.some(([, variables]) => variables?.search === 'pending search')).toBe(true))
  expect(location.hash).toBe(destination)
})

test('schema field sort reaches GraphQL and resets when switching to all content', async () => {
  setup()
  await screen.findByRole('button',{name:'Edit'})
  fireEvent.change(screen.getByLabelText('Content type'), {target:{value:'article'}})
  fireEvent.change(screen.getByLabelText('Sort entries'), {target:{value:'field:title:desc'}})
  await waitFor(() => expect(vi.mocked(gql).mock.calls.some(([query, variables]) => query.includes('orderBy:$orderBy') && (variables as any)?.orderBy?.field === 'title' && (variables as any)?.orderBy?.direction === 'DESC')).toBe(true))
  expect(location.hash).toContain('sort=field%3Atitle%3Adesc')
  fireEvent.change(screen.getByLabelText('Content type'), {target:{value:''}})
  await waitFor(() => expect((screen.getByLabelText('Sort entries') as HTMLSelectElement).value).toBe('updated_desc'))
  expect(location.hash).not.toContain('field%3A')
})

test('a hebrew title suggests the normalized slug', async () => {
  const { EntryEditor } = await import('./EntryEditor')
  vi.mocked(gql).mockImplementation(async () => ({ entries: { nodes: [] }, assets: [] }))
  render(<EntryEditor entry={null} initialType="article" types={types} editable onClose={vi.fn()} onSaved={vi.fn()} />)
  fireEvent.change(screen.getByLabelText(/^title/), { target: { value: 'מדריך התקנה' } })
  const slugInput = screen.getByLabelText(/^Slug/) as HTMLInputElement
  expect(slugInput.value).toBe('מדריך-התקנה')
  fireEvent.change(slugInput, { target: { value: 'React במובייל 2026' } })
  expect(slugInput.value).toBe('react-במובייל-2026')
})
