import { describe, expect, it, vi, afterEach, beforeEach } from 'vitest'
import { render, screen, fireEvent, cleanup, act } from '@testing-library/react'
import { RevisionCompare, type Revision } from './RevisionCompare'
import type { ContentType, Entry, Asset } from '../lib/api'
import * as api from '../lib/api'

beforeEach(() => { vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('Lookup unavailable in test')) })
afterEach(() => { cleanup(); vi.restoreAllMocks() })

const mockType: ContentType = {
  id: 'article-type',
  version: 1,
  key: 'article',
  name: 'Article',
  fields: [
    { name: 'summary', type: 'text', label: 'Summary', required: false },
    { name: 'content', type: 'richText', label: 'Article Body', required: false },
    { name: 'heroImage', type: 'asset', label: 'Hero Image', required: false },
    { name: 'authorRef', type: 'reference', label: 'Author', required: false },
    { name: 'tags', type: 'list', label: 'Tags', required: false },
    { name: 'metadata', type: 'object', label: 'Metadata', required: false },
  ],
}

const mockAssets: Asset[] = [
  { id: 'asset-1', name: 'banner.png', mime: 'image/png', size: 1048576, url: '/media/banner.png' },
]

const mockReferences: Entry[] = [
  {
    id: 'author-1',
    typeKey: 'author',
    slug: 'jane-doe',
    title: 'Jane Doe',
    data: {},
    version: 1,
    status: 'published',
    isLive: true,
    hasUnpublishedChanges: false,
    updatedAt: '2026-10-01T12:00:00Z',
  },
]

const sampleEntry: Entry = {
  id: 'entry-1',
  typeKey: 'article',
  slug: 'my-new-article',
  title: 'My New Article (Draft)',
  data: {
    summary: 'Updated draft summary',
    content: '# Hello world\nThis is **new draft** content.',
    heroImage: 'asset-1',
    authorRef: 'author-1',
    tags: ['news', 'tech'],
    metadata: { views: 42 },
  },
  version: 3,
  status: 'draft',
  isLive: true,
  hasUnpublishedChanges: true,
  updatedAt: '2026-10-11T12:00:00Z',
  publishedRevision: 1,
  publishedAt: '2026-10-01T10:00:00Z',
  publishedSlug: 'my-first-article',
  publishedTitle: 'My First Article (Live)',
  publishedData: {
    summary: 'Original live summary',
    content: '# Old title\nOld live text.',
    heroImage: 'asset-missing',
    authorRef: 'author-deleted',
    tags: ['news'],
    metadata: { views: 10 },
    legacyCustomField: 'old value from deleted schema field',
  },
}

const sampleRevisions: Revision[] = [
  {
    number: 1,
    snapshot: {
      slug: 'my-first-article',
      title: 'My First Article (Live)',
      data: {
        summary: 'Original live summary',
        content: '# Old title\nOld live text.',
        heroImage: 'asset-missing',
        authorRef: 'author-deleted',
        tags: ['news'],
      },
    },
    author: 'alice@example.com',
    createdAt: '2026-10-01T10:00:00Z',
  },
  {
    number: 2,
    snapshot: {
      slug: 'my-intermediate-article',
      title: 'My Intermediate Article',
      data: {
        summary: 'Middle summary',
        content: 'Mid text.',
        tags: ['news', 'draft'],
      },
    },
    author: 'bob@example.com',
    createdAt: '2026-10-05T14:30:00Z',
  },
]

describe('RevisionCompare', () => {
  it('renders Draft vs Live comparison with slug, title, rich text, and removed schema fields', () => {
    const handleRestore = vi.fn()
    const handleClose = vi.fn()

    render(
      <RevisionCompare
        entry={sampleEntry}
        definition={mockType}
        revisions={sampleRevisions}
        references={mockReferences}
        assets={mockAssets}
        role="editor"
        onClose={handleClose}
        onRestore={handleRestore}
      />
    )

    // Check modal headers
    expect(screen.getAllByText('Live Published Content').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Current Saved Draft').length).toBeGreaterThan(0)
    expect(screen.getByText('Revision 1')).toBeDefined()
    expect(screen.getByText('Version 3')).toBeDefined()

    // Title diff
    expect(screen.getByText('My First Article (Live)')).toBeDefined()
    expect(screen.getByText('My New Article (Draft)')).toBeDefined()

    // Slug diff
    expect(screen.getByText('my-first-article')).toBeDefined()
    expect(screen.getByText('my-new-article')).toBeDefined()

    // Summary diff
    expect(screen.getByText('Original live summary')).toBeDefined()
    expect(screen.getByText('Updated draft summary')).toBeDefined()

    // Removed schema field handling
    expect(screen.getByText(/legacyCustomField \(removed schema field\)/)).toBeDefined()
    expect(screen.getByText('old value from deleted schema field')).toBeDefined()

    // Asset & reference labels with missing/inaccessible fallback
    expect(screen.getByText(/banner\.png/)).toBeDefined()
    expect(screen.getByText(/Inaccessible asset \(asset-missing\)/)).toBeDefined()
    expect(screen.getByText(/Jane Doe \(\/jane-doe\)/)).toBeDefined()
    expect(screen.getByText(/Deleted or inaccessible entry \(author-deleted\)/)).toBeDefined()
  })

  it('allows collapsing unchanged fields and switching to raw JSON view', () => {
    render(
      <RevisionCompare
        entry={sampleEntry}
        definition={mockType}
        revisions={sampleRevisions}
        references={mockReferences}
        assets={mockAssets}
        role="editor"
        onClose={vi.fn()}
        onRestore={vi.fn()}
      />
    )

    // Check raw JSON view toggle
    const rawToggle = screen.getByRole('button', { name: 'Raw JSON' })
    fireEvent.click(rawToggle)
    expect(screen.getByText('Left Snapshot')).toBeDefined()
    expect(screen.getByText('Right Snapshot')).toBeDefined()

    // Switch back to structured view
    fireEvent.click(screen.getByRole('button', { name: 'Structured view' }))
    expect(screen.queryByText('Left Snapshot')).toBeNull()
    expect(screen.getByText('FIELD')).toBeDefined()

    // Check hide unchanged checkbox
    const hideCheckbox = screen.getByLabelText(/Hide unchanged fields/) as HTMLInputElement
    expect(hideCheckbox.checked).toBe(false)
    fireEvent.click(hideCheckbox)
    expect(hideCheckbox.checked).toBe(true)
  })

  it('allows comparing two historical revisions', () => {
    render(
      <RevisionCompare
        entry={sampleEntry}
        definition={mockType}
        revisions={sampleRevisions}
        references={mockReferences}
        assets={mockAssets}
        role="editor"
        onClose={vi.fn()}
        onRestore={vi.fn()}
      />
    )

    // Switch to revisions tab
    const revTab = screen.getByRole('tab', { name: /Compare two saved revisions/ })
    fireEvent.click(revTab)

    expect(screen.getByLabelText('Base revision')).toBeDefined()
    expect(screen.getByLabelText('Comparison revision')).toBeDefined()
    expect(screen.getByText(/By alice@example\.com/)).toBeDefined()
    expect(screen.getByText(/By bob@example\.com/)).toBeDefined()
  })

  it('explains restore impact and confirms restoring a revision as a draft', async () => {
    const handleRestore = vi.fn().mockResolvedValue(undefined)
    const handleClose = vi.fn()

    render(
      <RevisionCompare
        entry={sampleEntry}
        definition={mockType}
        revisions={sampleRevisions}
        references={mockReferences}
        assets={mockAssets}
        role="editor"
        onClose={handleClose}
        onRestore={handleRestore}
      />
    )

    // Click restore live revision button
    const restoreBtn = screen.getByRole('button', { name: /Restore live revision \(v1\) as draft/ })
    fireEvent.click(restoreBtn)

    // Confirmation banner should be displayed
    const alert = screen.getByRole('alert')
    expect(alert.textContent).toContain('Confirm restore of Revision 1')
    expect(alert.textContent).toContain('create a new draft (Version 4)')
    expect(alert.textContent).toContain('currently live website content and any scheduled publications remain safe')
    expect(alert.textContent).toContain('Current schema validations will apply')

    // Confirm button
    const confirmBtn = screen.getByRole('button', { name: 'Confirm and restore v1 as draft' })
    fireEvent.click(confirmBtn)

    expect(handleRestore).toHaveBeenCalledWith(1)
  })

  it('prevents reader role from triggering restores but allows inspection', () => {
    render(
      <RevisionCompare
        entry={sampleEntry}
        definition={mockType}
        revisions={sampleRevisions}
        references={mockReferences}
        assets={mockAssets}
        role="reader"
        onClose={vi.fn()}
        onRestore={vi.fn()}
      />
    )

    // Restore buttons should not exist for readers
    expect(screen.queryByRole('button', { name: /Restore/ })).toBeNull()

    // Role limitation note should be present
    expect(screen.getByText(/Readers can inspect revision differences but cannot restore revisions\./)).toBeDefined()

    // Can still view diffs
    expect(screen.getByText('Original live summary')).toBeDefined()
  })

  it('handles unpublished entries gracefully in draft vs live mode', () => {
    const unpublishedEntry: Entry = {
      ...sampleEntry,
      isLive: false,
      publishedRevision: undefined,
      publishedAt: undefined,
      publishedSlug: undefined,
      publishedTitle: undefined,
      publishedData: undefined,
    }

    render(
      <RevisionCompare
        entry={unpublishedEntry}
        definition={mockType}
        revisions={sampleRevisions}
        references={mockReferences}
        assets={mockAssets}
        role="editor"
        onClose={vi.fn()}
        onRestore={vi.fn()}
      />
    )

    expect(screen.getByText('Not published')).toBeDefined()
    expect(screen.getByText('Entry is not published live yet')).toBeDefined()
  })
})

it('labels nested and localized Markdown and array positions without exposing HTML markup', () => {
  const type: ContentType = { id: 'nested', key: 'article', name: 'Article', version: 1, fields: [
    { name: 'details', label: 'Details', type: 'object', fields: [{ name: 'body', label: 'Body', type: 'richText', localized: true }] },
    { name: 'steps', label: 'Steps', type: 'list', item: { name: '', type: 'text' } },
  ] }
  const entry: Entry = { ...sampleEntry, data: { details: { body: { he: '**חדש**<script>bad()</script>' } }, steps: ['B', 'A'] }, publishedSnapshot: { slug: 'before', title: 'Before', revision: 1, data: { details: { body: { he: 'ישן' } }, steps: ['A', 'B'] } }, publishedData: undefined }
  render(<RevisionCompare entry={entry} definition={type} revisions={[]} references={[]} assets={[]} role="reader" onClose={vi.fn()} onRestore={vi.fn()} />)
  expect(screen.getByText('Details › Body (he)')).toBeTruthy()
  expect(screen.getByText('Steps › Item 1')).toBeTruthy()
  expect(screen.getByText('Steps › Item 2')).toBeTruthy()
  expect(document.querySelector('script')).toBeNull()
  expect(document.querySelector('.diff-markdown strong')?.textContent).toBe('חדש')
})


it('resolves a reference and asset outside the initial result page using their IDs', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (_url, options) => {
    const { query } = JSON.parse(String(options?.body))
    const data = query.includes('assetPage') ? { assetPage: { nodes: [{ id: 'late-asset', name: 'Later banner.png', mime: 'image/png', size: 2048, url: '/media/later.png' }] } } : { entry: { ...sampleEntry, id: 'late-reference', title: 'Later author', slug: 'later-author' } }
    return { ok: true, json: async () => ({ data }) } as Response
  })
  const entry = { ...sampleEntry, data: { authorRef: 'late-reference', heroImage: 'late-asset' }, publishedData: null, publishedSnapshot: null }
  render(<RevisionCompare entry={entry} definition={mockType} revisions={[]} references={[]} assets={[]} role="reader" onClose={vi.fn()} onRestore={vi.fn()} />)
  expect(await screen.findByText(/Later author/)).toBeTruthy()
  expect(await screen.findByText(/Later banner.png/)).toBeTruthy()
})

it('keeps the restore confirmation open and announces a rejected restore', async () => {
  const close = vi.fn()
  const restore = vi.fn().mockRejectedValue(new Error('Current schema requires a subtitle.'))
  render(<RevisionCompare entry={sampleEntry} definition={mockType} revisions={sampleRevisions} references={mockReferences} assets={mockAssets} role="editor" onClose={close} onRestore={restore} />)
  fireEvent.click(screen.getByRole('button', { name: /Restore live revision/ }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm and restore v1 as draft' }))
  expect(await screen.findByText('Current schema requires a subtitle.')).toBeTruthy()
  expect(close).not.toHaveBeenCalled()
})

it('moves tab focus and selection with arrows, Home and End while keeping one tab stop', () => {
  render(<RevisionCompare entry={sampleEntry} definition={mockType} revisions={sampleRevisions} references={mockReferences} assets={mockAssets} role="editor" onClose={vi.fn()} onRestore={vi.fn()} />)
  const live = screen.getByRole('tab', { name: 'Draft vs Live content' })
  const revisions = screen.getByRole('tab', { name: /Compare two saved revisions/ })
  live.focus()
  for (const [key, target] of [
    ['ArrowRight', revisions], ['ArrowRight', live], ['ArrowLeft', revisions],
    ['Home', live], ['End', revisions],
  ] as const) {
    fireEvent.keyDown(document.activeElement!, { key })
    expect(document.activeElement).toBe(target)
    expect(target.getAttribute('aria-selected')).toBe('true')
    expect(target.tabIndex).toBe(0)
    expect((target === live ? revisions : live).tabIndex).toBe(-1)
  }
  expect(screen.getByLabelText('Base revision')).toBeTruthy()
})

it('skips the disabled revisions tab when there is only one saved revision', () => {
  render(<RevisionCompare entry={sampleEntry} definition={mockType} revisions={sampleRevisions.slice(0, 1)} references={mockReferences} assets={mockAssets} role="editor" onClose={vi.fn()} onRestore={vi.fn()} />)
  const live = screen.getByRole('tab', { name: 'Draft vs Live content' })
  const revisions = screen.getByRole<HTMLButtonElement>('tab', { name: /Compare two saved revisions/ })
  live.focus()
  for (const key of ['ArrowRight', 'ArrowLeft', 'Home', 'End']) {
    fireEvent.keyDown(live, { key })
    expect(document.activeElement).toBe(live)
    expect(live.getAttribute('aria-selected')).toBe('true')
  }
  expect(revisions.disabled).toBe(true)
  expect(revisions.tabIndex).toBe(-1)
  expect(screen.queryByLabelText('Base revision')).toBeNull()
})

it.each(['live', 'left', 'right'])('returns Cancel focus to the %s restore opener without restoring', position => {
  const restore = vi.fn(), close = vi.fn()
  render(<RevisionCompare entry={sampleEntry} definition={mockType} revisions={sampleRevisions} references={mockReferences} assets={mockAssets} role="editor" onClose={close} onRestore={restore} />)
  if (position !== 'live') fireEvent.click(screen.getByRole('tab', { name: /Compare two saved revisions/ }))
  const opener = screen.getByRole('button', { name: position === 'live' ? /Restore live revision/ : `Restore v${position === 'left' ? 2 : 1} as draft` })
  opener.focus()
  fireEvent.click(opener)
  const cancel = screen.getByRole('button', { name: 'Cancel' })
  cancel.focus()
  fireEvent.click(cancel)
  expect(screen.queryByRole('button', { name: 'Cancel' })).toBeNull()
  expect(document.activeElement).toBe(opener)
  expect(restore).not.toHaveBeenCalled()
  expect(close).not.toHaveBeenCalled()
})

describe('revision ID lookup lifecycle', () => {
  const entry: Entry = {
    ...sampleEntry,
    data: { authorRef: 'late-reference', heroImage: 'late-asset' },
    publishedData: { authorRef: 'author-1', heroImage: 'asset-1' },
    publishedSnapshot: null,
  }
  const props = {
    entry, definition: mockType, revisions: [], references: mockReferences, assets: mockAssets,
    role: 'reader', onClose: vi.fn(), onRestore: vi.fn(),
  }
  const lateReference = { ...mockReferences[0], id: 'late-reference', title: 'Resolved author' }
  const lateAsset = { ...mockAssets[0], id: 'late-asset', name: 'Resolved image.png' }

  function deferred<T>() {
    let resolve!: (value: T) => void
    let reject!: (reason: unknown) => void
    const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
    return { promise, resolve, reject }
  }

  it('skips supplied rows and resolves missing IDs using the context captured on mount', async () => {
    const original = api.getContext()
    const reference = deferred<{ entry: Entry }>()
    const asset = deferred<{ assetPage: { nodes: Asset[] } }>()
    const nextReference = deferred<{ entry: Entry }>()
    const nextAsset = deferred<{ assetPage: { nodes: Asset[] } }>()
    const lookup = vi.spyOn(api, 'gql')
      .mockReturnValueOnce(reference.promise)
      .mockReturnValueOnce(asset.promise)
      .mockReturnValueOnce(nextReference.promise)
      .mockReturnValueOnce(nextAsset.promise)
    try {
      api.setContext('original-project', 'original-csrf')
      const view = render(<RevisionCompare {...props} />)
      expect(lookup.mock.calls.map(([, variables]) => variables?.id)).toEqual(['late-reference', 'late-asset'])
      api.setContext('new-project', 'new-csrf')
      view.rerender(<RevisionCompare {...props} assets={[...mockAssets]} />)
      expect(lookup).toHaveBeenCalledTimes(4)
      expect(lookup.mock.calls.map(([, , context]) => context)).toEqual(Array(4).fill({
        project: 'original-project', csrf: 'original-csrf',
      }))
      await act(async () => {
        nextReference.resolve({ entry: lateReference })
        nextAsset.resolve({ assetPage: { nodes: [lateAsset] } })
      })
      expect(screen.getByText(/Resolved author/)).toBeTruthy()
      expect(screen.getByText(/Resolved image.png/)).toBeTruthy()
    } finally {
      api.setContext(original.project, original.csrf)
    }
  })

  it('ignores superseded lookup responses after rerender, preserving the latest labels', async () => {
    const reference = deferred<{ entry: Entry }>()
    const asset = deferred<{ assetPage: { nodes: Asset[] } }>()
    const nextReference = deferred<{ entry: Entry }>()
    const nextAsset = deferred<{ assetPage: { nodes: Asset[] } }>()
    vi.spyOn(api, 'gql')
      .mockReturnValueOnce(reference.promise)
      .mockReturnValueOnce(asset.promise)
      .mockReturnValueOnce(nextReference.promise)
      .mockReturnValueOnce(nextAsset.promise)
    const view = render(<RevisionCompare {...props} />)
    view.rerender(<RevisionCompare {...props} references={[...mockReferences]} />)
    await act(async () => {
      nextReference.resolve({ entry: lateReference })
      nextAsset.resolve({ assetPage: { nodes: [lateAsset] } })
    })
    await act(async () => {
      reference.resolve({ entry: { ...lateReference, title: 'Stale author' } })
      asset.resolve({ assetPage: { nodes: [{ ...lateAsset, name: 'Stale image.png' }] } })
    })
    expect(screen.getByText(/Resolved author/)).toBeTruthy()
    expect(screen.getByText(/Resolved image.png/)).toBeTruthy()
    expect(screen.queryByText(/Stale author/)).toBeNull()
    expect(screen.queryByText(/Stale image.png/)).toBeNull()
  })

  it('does not read late response values after unmount', async () => {
    const reference = deferred<{ entry: Entry }>()
    const asset = deferred<{ assetPage: { nodes: Asset[] } }>()
    vi.spyOn(api, 'gql').mockReturnValueOnce(reference.promise).mockReturnValueOnce(asset.promise)
    const view = render(<RevisionCompare {...props} />)
    view.unmount()
    const readReference = vi.fn(() => lateReference)
    const readAssetPage = vi.fn(() => ({ nodes: [lateAsset] }))
    await act(async () => {
      reference.resolve({ get entry() { return readReference() } })
      asset.resolve({ get assetPage() { return readAssetPage() } })
    })
    expect(readReference).not.toHaveBeenCalled()
    expect(readAssetPage).not.toHaveBeenCalled()
  })

  it.each(['missing', 'rejected'] as const)('retains inaccessible labels for %s lookup results', async result => {
    const reference = deferred<{ entry: Entry | null }>()
    const asset = deferred<{ assetPage: { nodes: Asset[] } }>()
    vi.spyOn(api, 'gql').mockReturnValueOnce(reference.promise).mockReturnValueOnce(asset.promise)
    render(<RevisionCompare {...props} />)
    await act(async () => {
      if (result === 'missing') {
        reference.resolve({ entry: null })
        asset.resolve({ assetPage: { nodes: [] } })
      } else {
        reference.reject(new Error('Reference lookup failed'))
        asset.reject(new Error('Asset lookup failed'))
      }
    })
    expect(screen.getByText('Deleted or inaccessible entry (late-reference)')).toBeTruthy()
    expect(screen.getByText('Inaccessible asset (late-asset)')).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
  })
})
