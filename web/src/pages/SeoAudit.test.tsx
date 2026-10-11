import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { gql, setContext, type Entry } from '../lib/api'
import { SeoAudit } from './SeoAudit'
import { SeoEntryPanel } from '../components/SeoEntryPanel'
import { focusSeoField, seoEntryLink, type SeoFinding, type SeoReport } from '../lib/seo'
import { readContentRoute } from '../lib/navigation'

vi.mock('../lib/api', async original => ({ ...await original<typeof import('../lib/api')>(), gql: vi.fn() }))
const types = [{ id: 'type', key: 'article', name: 'Articles', version: 1, fields: [] }]
const finding: SeoFinding = { code: 'missing_title', severity: 'critical', entryId: 'entry', entryTitle: 'Article', typeKey: 'article', snapshot: 'live', revision: 2, locale: 'he', fieldPath: 'data.items[0].title.he', explanation: 'The title is missing.', guidance: 'Write a descriptive title.' }
const report: SeoReport = { snapshot: 'live', generatedAt: '2026-10-11T12:00:00Z', revision: null, recordCount: 2, pageCount: 1, supportingCount: 0, needsMappingCount: 1, noLiveCount: 3, criticalCount: 1, warningCount: 0, infoCount: 0, mappings: [{ typeKey: 'article', name: 'Articles', kind: 'needs_mapping', titlePath: null, descriptionPath: 'description' }], notChecked: ['Website HTML', 'Indexing', 'Captured schedules'], findings: [finding], total: 1, endCursor: null, hasNextPage: false }
const entry: Entry = { id: 'entry', typeKey: 'article', slug: 'entry', title: 'Article', data: {}, status: 'draft', version: 4, updatedAt: '', isLive: true, hasUnpublishedChanges: true }
beforeEach(() => { vi.mocked(gql).mockReset(); setContext('workspace', 'csrf'); vi.mocked(gql).mockResolvedValue({ seoAudit: report, seoEntryAudit: { ...report, snapshot: 'draft', revision: 4 } }) })
afterEach(() => { cleanup(); history.replaceState(null, '', '/'); vi.restoreAllMocks() })

test('defaults to live and shows coverage gaps, actionable links, and unchecked areas', async () => {
  render(<SeoAudit types={types} projectId="workspace" />)
  await screen.findByText('The title is missing.')
  expect(screen.getByText(/1 need mapping/)).toBeTruthy()
  expect(screen.getByText(/3 records have no live snapshot/)).toBeTruthy()
  expect(screen.getByText('Website HTML · Indexing · Captured schedules')).toBeTruthy()
  const link = screen.getByRole('link', { name: 'Open draft to fix' }) as HTMLAnchorElement
  const route = readContentRoute(undefined, link.hash)
  expect(route).toMatchObject({ workspace: 'workspace', entry: 'entry', field: finding.fieldPath, seoSnapshot: 'live' })
  expect(vi.mocked(gql).mock.calls[0][1]).toMatchObject({ snapshot: 'live', after: null })
})

test('filters and pagination rerun in the selected snapshot and reset the cursor', async () => {
  vi.mocked(gql).mockResolvedValue({ seoAudit: { ...report, hasNextPage: true, endCursor: 'page-2' } })
  render(<SeoAudit types={types} projectId="workspace" />)
  await screen.findByText('The title is missing.')
  fireEvent.click(screen.getByRole('button', { name: 'Next findings' }))
  await waitFor(() => expect(vi.mocked(gql).mock.calls[vi.mocked(gql).mock.calls.length - 1]?.[1]).toMatchObject({ after: 'page-2' }))
  await screen.findByText('Page 2')
  fireEvent.change(screen.getByLabelText('Version'), { target: { value: 'draft' } })
  await waitFor(() => expect(vi.mocked(gql).mock.calls[vi.mocked(gql).mock.calls.length - 1]?.[1]).toMatchObject({ snapshot: 'draft', after: null }))
  fireEvent.change(screen.getByLabelText('Content type'), { target: { value: 'article' } })
  fireEvent.change(screen.getByLabelText('Severity'), { target: { value: 'warning' } })
  await waitFor(() => expect(vi.mocked(gql).mock.calls[vi.mocked(gql).mock.calls.length - 1]?.[1]).toMatchObject({ type: 'article', severity: 'warning', after: null }))
  await screen.findByText('The title is missing.')
  const count = vi.mocked(gql).mock.calls.length
  fireEvent.click(screen.getByRole('button', { name: 'Rerun audit' }))
  await waitFor(() => expect(vi.mocked(gql).mock.calls.length).toBeGreaterThan(count))
})

test('shows loading and retryable errors without presenting a clean report', async () => {
  let reject!: (error: Error) => void
  vi.mocked(gql).mockImplementationOnce(() => new Promise((_, fail) => { reject = fail }))
  render(<SeoAudit types={types} projectId="workspace" />)
  expect(screen.getByRole('status').textContent).toContain('Checking live snapshots')
  await act(async () => reject(new Error('Audit unavailable')))
  expect(screen.getByRole('alert').textContent).toContain('Audit unavailable')
  expect(screen.queryByText(/No findings in the evaluated record checks/)).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Retry audit' }))
  await screen.findByText('The title is missing.')
})

test('separates empty snapshots from filters with no findings', async () => {
  vi.mocked(gql).mockResolvedValue({ seoAudit: { ...report, recordCount: 0, findings: [], total: 0 } })
  render(<SeoAudit types={types} projectId="workspace" />)
  await screen.findByText('No live records to audit.')
  vi.mocked(gql).mockResolvedValue({ seoAudit: { ...report, findings: [], total: 0 } })
  fireEvent.change(screen.getByLabelText('Severity'), { target: { value: 'info' } })
  await screen.findByText('No findings match these filters.')
})

test('late responses from the previous workspace cannot populate the current report', async () => {
  let resolve!: (value: unknown) => void
  vi.mocked(gql).mockImplementationOnce(() => new Promise(done => { resolve = done }))
  const view = render(<SeoAudit types={types} projectId="old" />)
  setContext('new', 'csrf')
  vi.mocked(gql).mockResolvedValue({ seoAudit: { ...report, findings: [], total: 0 } })
  view.rerender(<SeoAudit types={types} projectId="new" />)
  await screen.findByText(/No findings in the evaluated record checks/)
  await act(async () => resolve({ seoAudit: report }))
  expect(screen.queryByText('The title is missing.')).toBeNull()
})

test('saved-draft panel marks unsaved changes stale and refreshes with the saved revision', async () => {
  const view = render(<SeoEntryPanel entry={entry} dirty={false} projectId="workspace" />)
  await screen.findByText('Saved draft revision 4 · advisory checks')
  view.rerender(<SeoEntryPanel entry={entry} dirty projectId="workspace" />)
  expect(screen.getByRole('status').textContent).toContain('Results are stale')
  vi.mocked(gql).mockResolvedValue({ seoEntryAudit: { ...report, snapshot: 'draft', revision: 5 } })
  view.rerender(<SeoEntryPanel entry={{ ...entry, version: 5 }} dirty={false} projectId="workspace" />)
  await screen.findByText('Saved draft revision 5 · advisory checks')
  expect(screen.queryByText(/Results are stale/)).toBeNull()
  expect(vi.mocked(gql).mock.calls[vi.mocked(gql).mock.calls.length - 1]?.[1]).toMatchObject({ id: 'entry', after: null })
})

test('field links retain nested localized paths and focus the matching control', () => {
  const input = document.createElement('input')
  input.id = `field-${encodeURIComponent(finding.fieldPath!)}`
  document.body.append(input)
  focusSeoField(finding.fieldPath)
  expect(document.activeElement).toBe(input)
  expect(readContentRoute(undefined, seoEntryLink(finding, 'workspace'))).toMatchObject({ field: finding.fieldPath, seoSnapshot: 'live' })
  input.remove()
})

test('unknown or absent field targets stop safely and missing translations focus their parent', () => {
  const parent = document.createElement('fieldset')
  parent.id = 'field-data.title'; parent.tabIndex = -1
  document.body.append(parent)
  focusSeoField('unmapped')
  focusSeoField('data.absent')
  focusSeoField(null)
  focusSeoField('data.title.he')
  expect(document.activeElement).toBe(parent)
  parent.remove()
})
