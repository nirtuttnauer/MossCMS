
const storage: Record<string, string> = {}
const mockLocalStorage = {
  getItem: (key: string) => storage[key] ?? null,
  setItem: (key: string, val: string) => { storage[key] = String(val) },
  removeItem: (key: string) => { delete storage[key] },
  clear: () => { for (const key of Object.keys(storage)) delete storage[key] },
}
Object.defineProperty(window, 'localStorage', { value: mockLocalStorage, writable: true })
Object.defineProperty(globalThis, 'localStorage', { value: mockLocalStorage, writable: true })

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { OnboardingChecklist } from './OnboardingChecklist'
import { gql, type ContentType, type Project } from '../lib/api'

vi.mock('../lib/api', async importOriginal => ({
  ...(await importOriginal<typeof import('../lib/api')>()),
  gql: vi.fn(),
}))

describe('OnboardingChecklist (TASK-35 / MC-35)', () => {
  const adminProject: Project = {
    id: 'proj-1',
    name: 'Main Workspace',
    role: 'admin',
  }

  const otherProject: Project = {
    id: 'proj-2',
    name: 'Second Workspace',
    role: 'admin',
  }

  const emptyOverview = {
    total: 0,
    published: 0,
    drafts: 0,
    scheduled: 0,
    types: 0,
    assets: 0,
    members: 1,
  }

  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
    globalThis.fetch = vi.fn()
  })

  afterEach(() => { cleanup(); vi.unstubAllGlobals() })

  it('shows four steps with one actionable next step for empty admin workspace and survives dismissal per-workspace', () => {
    const { rerender } = render(
      <OnboardingChecklist
        project={adminProject}
        userId="user-1"
        role="admin"
        types={[]}
        overview={emptyOverview}
        onChanged={vi.fn()}
      />
    )

    // All 4 steps are visible
    expect(screen.getByText('Choose or define a content type')).toBeTruthy()
    expect(screen.getByText('Draft your first entry')).toBeTruthy()
    expect(screen.getByText('Publish an entry')).toBeTruthy()
    expect(screen.getByText('Verify delivery query with a delivery token')).toBeTruthy()

    // Step 1 is the active step
    const step1 = screen.getByText('Choose or define a content type').closest('li')!
    expect(step1.getAttribute('aria-current')).toBe('step')
    expect(step1.className).toContain('active')

    // Admin has starter template buttons
    expect(screen.getByRole('button', { name: 'Add Article' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Add Product' })).toBeTruthy()

    // Dismissal
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss checklist' }))
    expect(screen.queryByText('First published entry checklist')).toBeNull()
    expect(screen.getByRole('button', { name: 'Resume getting started guide' })).toBeTruthy()

    // Dismissal persists on reload for this workspace
    rerender(
      <OnboardingChecklist
        project={adminProject}
        userId="user-1"
        role="admin"
        types={[]}
        overview={emptyOverview}
        onChanged={vi.fn()}
      />
    )
    expect(screen.getByRole('button', { name: 'Resume getting started guide' })).toBeTruthy()

    // Switching to a second workspace is NOT dismissed and shows its own fresh state
    rerender(
      <OnboardingChecklist
        project={otherProject}
        userId="user-1"
        role="admin"
        types={[]}
        overview={emptyOverview}
        onChanged={vi.fn()}
      />
    )
    expect(screen.getByText('First published entry checklist')).toBeTruthy()
    expect(screen.getByText(/Follow these 4 steps to set up and verify content delivery in Second Workspace/)).toBeTruthy()
  })

  it('infers completion from real state; draft saves never satisfy publish step; adapts to role', () => {
    const types: ContentType[] = [
      { id: 't1', key: 'article', name: 'Articles', version: 1, fields: [] },
    ]

    // 1 draft entry, 0 published entries
    const draftOverview = {
      total: 1,
      published: 0,
      drafts: 1,
      scheduled: 0,
      types: 1,
      assets: 0,
      members: 1,
    }

    render(
      <OnboardingChecklist
        project={adminProject}
        userId="user-1"
        role="admin"
        types={types}
        overview={draftOverview}
        onChanged={vi.fn()}
      />
    )

    // Step 1 and Step 2 should be marked done
    expect(screen.getByText('Completed (1 defined)')).toBeTruthy()
    expect(screen.getByText('Completed (1 entries)')).toBeTruthy()

    // Step 3 must NOT be satisfied by draft saves
    const step3 = screen.getByText('Publish an entry').closest('li')!
    expect(step3.className).toContain('active')
    expect(step3.getAttribute('aria-current')).toBe('step')
    expect(screen.getByText(/Draft saves do not satisfy publication/)).toBeTruthy()
  })

  it('restricts actions for reader role and explains permissions', () => {
    render(
      <OnboardingChecklist
        project={adminProject}
        userId="user-1"
        role="reader"
        types={[]}
        overview={emptyOverview}
        onChanged={vi.fn()}
      />
    )

    expect(screen.queryByRole('button', { name: 'Add Article' })).toBeNull()
    expect(screen.getByText(/Readers cannot create content types/)).toBeTruthy()
  })

  it('does not offer schema creation to editors', () => {
    render(<OnboardingChecklist project={adminProject} userId="user-1" role="editor" types={[]} overview={emptyOverview} onChanged={vi.fn()} />)
    expect(screen.queryByRole('button', { name: 'Add Article' })).toBeNull()
    expect(screen.getByText(/Editors cannot create content types/)).toBeTruthy()
  })

  it('does not verify an empty delivery response or content from another workspace', async () => {
    const types: ContentType[] = [{ id: 't', key: 'article', name: 'Article', version: 1, fields: [] }]
    render(<OnboardingChecklist project={adminProject} userId="user-1" role="admin" types={types} overview={{ ...emptyOverview, total: 1, published: 1 }} onChanged={vi.fn()} />)
    vi.mocked(globalThis.fetch).mockResolvedValueOnce({ ok: true, json: async () => ({ data: { entries: { nodes: [] } } }) } as Response)
    fireEvent.change(screen.getByLabelText('Delivery token'), { target: { value: 'synthetic-token' } })
    fireEvent.click(screen.getByRole('button', { name: 'Test delivery query' }))
    expect((await screen.findByRole('alert')).textContent).toContain('No published entry')
    expect(localStorage.getItem('moss-onboarding-verified-user-1-proj-1')).toBeNull()
    vi.mocked(globalThis.fetch).mockResolvedValueOnce({ ok: true, json: async () => ({ data: { entries: { nodes: [{ id: 'foreign' }] } } }) } as Response)
    vi.mocked(gql).mockResolvedValueOnce({ entry: null })
    fireEvent.click(screen.getByRole('button', { name: 'Test delivery query' }))
    await screen.findByText('Connection error: Use a delivery token for this workspace and a currently published entry.')
    expect(localStorage.getItem('moss-onboarding-verified-user-1-proj-1')).toBeNull()
  })

  it('ignores a delivery response after switching workspaces', async () => {
    const types: ContentType[] = [{ id: 't', key: 'article', name: 'Article', version: 1, fields: [] }]
    const overview = { ...emptyOverview, total: 1, published: 1 }
    let finish!: (response: Response) => void
    vi.mocked(globalThis.fetch).mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    const { rerender } = render(<OnboardingChecklist project={adminProject} userId="user-1" role="admin" types={types} overview={overview} onChanged={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('Delivery token'), { target: { value: 'synthetic-token' } })
    fireEvent.click(screen.getByRole('button', { name: 'Test delivery query' }))
    rerender(<OnboardingChecklist project={otherProject} userId="user-1" role="admin" types={types} overview={overview} onChanged={vi.fn()} />)
    finish({ ok: true, json: async () => ({ data: { entries: { nodes: [{ id: 'one' }] } } }) } as Response)
    await waitFor(() => expect((screen.getByLabelText('Delivery token') as HTMLInputElement).value).toBe(''))
    expect(localStorage.getItem('moss-onboarding-verified-user-1-proj-2')).toBeNull()
  })

  it('verifies published-only delivery query with user token without leaking token or marking false success', async () => {
    const timeoutSignal = new AbortController().signal
    const timeout = vi.spyOn(AbortSignal, 'timeout').mockReturnValue(timeoutSignal)
    const types: ContentType[] = [
      { id: 't1', key: 'article', name: 'Articles', version: 1, fields: [] },
    ]
    const publishedOverview = {
      total: 1,
      published: 1,
      drafts: 0,
      scheduled: 0,
      types: 1,
      assets: 0,
      members: 1,
    }

    render(
      <OnboardingChecklist
        project={adminProject}
        userId="user-1"
        role="admin"
        types={types}
        overview={publishedOverview}
        onChanged={vi.fn()}
      />
    )

    const step4 = screen.getByText('Verify delivery query with a delivery token').closest('li')!
    expect(step4.className).toContain('active')

    const tokenInput = screen.getByLabelText('Delivery token')
    const testBtn = screen.getByRole('button', { name: 'Test delivery query' })

    // 1. Rejection test: invalid token response
    vi.mocked(globalThis.fetch).mockResolvedValueOnce({
      ok: false,
      status: 401,
      json: async () => ({ detail: 'A valid delivery token is required.' }),
    } as Response)

    fireEvent.change(tokenInput, { target: { value: 'bad_token_secret' } })
    fireEvent.click(testBtn)

    await screen.findByText('A valid delivery token is required.')
    expect(localStorage.getItem(`moss-onboarding-verified-user-1-${adminProject.id}`)).toBeNull()
    expect(screen.queryByText('Verified securely')).toBeNull()

    vi.mocked(gql).mockResolvedValueOnce({ entry: { id: "entry-1", isLive: true } })

    // 2. Successful verification test
    vi.mocked(globalThis.fetch).mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        data: {
          entries: {
            nodes: [{ id: 'entry-1', title: 'Hello World', slug: 'hello-world' }],
          },
        },
      }),
    } as Response)

    fireEvent.change(tokenInput, { target: { value: 'valid_delivery_token' } })
    fireEvent.click(testBtn)

    await screen.findByText(/Delivery verified:/)
    expect(localStorage.getItem(`moss-onboarding-verified-user-1-${adminProject.id}`)).toBe('true')
    expect(screen.getByText('Verified securely')).toBeTruthy()

    // Verify token was sent in Authorization header and NOT in URL
    const fetchCall = vi.mocked(globalThis.fetch).mock.calls[1]
    const [url, options] = fetchCall
    expect(url).toBe('/delivery/graphql')
    expect(String(url)).not.toContain('valid_delivery_token')
    expect((options?.headers as Record<string, string>)?.['Authorization']).toBe('Bearer valid_delivery_token')
    expect(timeout.mock.calls).toEqual([[30000], [30000]])
    expect(options?.signal).toBe(timeoutSignal)
  })
})
