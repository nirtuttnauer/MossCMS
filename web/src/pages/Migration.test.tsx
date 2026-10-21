import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { Migration } from './Migration'
import { rest, setContext } from '../lib/api'
import { exportArchive, type MigrationReport } from '../lib/migration'

vi.mock('../lib/api', async original => ({ ...await original<typeof import('../lib/api')>(), rest: vi.fn() }))
vi.mock('../lib/migration', async original => ({ ...await original<typeof import('../lib/migration')>(), exportArchive: vi.fn() }))
const project = { id: 'destination', name: 'New workspace', role: 'admin' as const }
const report: MigrationReport = { applied: false, validation: 'signed-review', importKey: 'key', counts: { schemas: 1, entries: 2, assets: 1, revisions: 3, provenance: 0 }, omittedFields: ['article.secret'], includePrivate: false, publication: 'drafts', sourceSchemas: [{ key: 'article', name: 'Article', version: 1, fields: [{ name: 'title', type: 'text' }] }], transformations: [{ entryId: 'source-entry', snapshot: 'draft', op: 'rename', path: 'data.old', step: 0 }] }
beforeEach(() => {
  vi.resetAllMocks(); setContext(project.id, 'csrf')
  vi.mocked(rest).mockImplementation(async path => path === '/api/migration/limits' ? { archiveBytes: 64 * 1024 * 1024, pipelineBytes: 256 * 1024 } : report)
  vi.mocked(exportArchive).mockResolvedValue()
})
afterEach(() => { cleanup(); vi.restoreAllMocks() })
function chooseFile(name = 'workspace.zip') { fireEvent.change(screen.getByLabelText('Workspace ZIP archive'), { target: { files: [new File(['archive'], name, { type: 'application/zip' })] } }) }
async function validate() { chooseFile(); await waitFor(() => expect((screen.getByRole('button', { name: 'Validate import' }) as HTMLButtonElement).disabled).toBe(false)); fireEvent.click(screen.getByRole('button', { name: 'Validate import' })); await screen.findByRole('heading', { name: 'Validation passed — review import' }) }

test('exports private content only when selected and waits for a reviewed import', async () => {
  const changed = vi.fn()
  render(<Migration project={project} onChanged={changed} />)
  expect(screen.queryByRole('button', { name: 'Import reviewed archive' })).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Download workspace ZIP' }))
  await waitFor(() => expect(exportArchive).toHaveBeenCalledWith(false, false))
  await screen.findByText('Your workspace archive is ready to download.')
  fireEvent.click(screen.getByLabelText('Include entry revision history')); fireEvent.click(screen.getByLabelText('Include private fields'))
  fireEvent.click(screen.getByRole('button', { name: 'Download workspace ZIP' }))
  await waitFor(() => expect(exportArchive).toHaveBeenLastCalledWith(true, true))
  await screen.findByText('Your workspace archive is ready to download.')
  await validate()
  const preview = vi.mocked(rest).mock.calls.find(([path]) => path === '/api/migration/import')!
  expect((preview[2] as FormData).get('apply')).toBe('false')
  expect((preview[2] as FormData).get('validation')).toBeNull()
  vi.mocked(rest).mockResolvedValue({ ...report, applied: true })
  fireEvent.click(screen.getByRole('button', { name: 'Import reviewed archive' }))
  expect(screen.getByRole('dialog').textContent).toContain('New workspace')
  expect(changed).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Confirm import' }))
  await screen.findByRole('heading', { name: 'Import complete' })
  const applied = vi.mocked(rest).mock.calls[vi.mocked(rest).mock.calls.length - 1][2] as FormData
  expect(applied.get('apply')).toBe('true'); expect(applied.get('validation')).toBe('signed-review')
  expect(changed).toHaveBeenCalledOnce()
})

test('editing, reordering, removing, or changing the archive invalidates the review', async () => {
  render(<Migration project={project} onChanged={vi.fn()} />)
  await validate()
  fireEvent.click(screen.getByRole('button', { name: 'Add step' }))
  expect(screen.queryByRole('button', { name: 'Import reviewed archive' })).toBeNull()
  fireEvent.change(screen.getByLabelText('Step 1 field path'), { target: { value: 'old' } })
  fireEvent.change(screen.getByLabelText('Step 1 new field name'), { target: { value: 'title' } })
  fireEvent.click(screen.getByRole('button', { name: 'Add step' }))
  fireEvent.change(screen.getByLabelText('Step 2 operation'), { target: { value: 'drop' } })
  fireEvent.change(screen.getByLabelText('Step 2 field path'), { target: { value: 'obsolete' } })
  fireEvent.click(screen.getByRole('button', { name: 'Move step 2 up' }))
  fireEvent.click(screen.getByRole('button', { name: 'Validate import' }))
  await screen.findByRole('heading', { name: 'Validation passed — review import' })
  const body = vi.mocked(rest).mock.calls[vi.mocked(rest).mock.calls.length - 1][2] as FormData
  expect(JSON.parse(body.get('pipeline') as string).steps).toEqual([{ op: 'drop', path: 'obsolete' }, { op: 'rename', path: 'old', to: 'title' }])
  expect(document.activeElement?.id).toBe('migration-review')
  fireEvent.click(screen.getByRole('button', { name: 'Remove step 1' }))
  expect(screen.queryByRole('button', { name: 'Import reviewed archive' })).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Validate import' }))
  await screen.findByRole('heading', { name: 'Validation passed — review import' })
  chooseFile('another.zip')
  expect(screen.queryByRole('button', { name: 'Import reviewed archive' })).toBeNull()
})

test('invalid JSON stays editable and focuses the error without making a request', async () => {
  render(<Migration project={project} onChanged={vi.fn()} />)
  chooseFile()
  await waitFor(() => expect((screen.getByRole('button', { name: 'Validate import' }) as HTMLButtonElement).disabled).toBe(false))
  fireEvent.change(screen.getByLabelText('Schema overrides (JSON)'), { target: { value: '{bad' } })
  fireEvent.click(screen.getByRole('button', { name: 'Validate import' }))
  expect((await screen.findByRole('alert')).textContent).toContain('Destination schemas must be valid JSON')
  expect(document.activeElement).toBe(screen.getByRole('alert'))
  expect(vi.mocked(rest).mock.calls.filter(([path]) => path === '/api/migration/import')).toHaveLength(0)
  expect((screen.getByLabelText('Schema overrides (JSON)') as HTMLTextAreaElement).value).toBe('{bad')
})

test('a stale response cannot restore an import review after unmount', async () => {
  let finish!: (value: MigrationReport) => void
  vi.mocked(rest).mockImplementation(async path => path.endsWith('/limits') ? { archiveBytes: 64 * 1024 * 1024, pipelineBytes: 256 * 1024 } : new Promise<MigrationReport>(resolve => { finish = resolve }))
  const changed = vi.fn()
  const view = render(<Migration project={project} onChanged={changed} />)
  chooseFile()
  await waitFor(() => expect((screen.getByRole('button', { name: 'Validate import' }) as HTMLButtonElement).disabled).toBe(false))
  fireEvent.click(screen.getByRole('button', { name: 'Validate import' })); view.unmount()
  await act(async () => finish({ ...report, applied: true }))
  expect(changed).not.toHaveBeenCalled()
})

test('editors have no archive controls or migration requests', () => {
  render(<Migration project={{ ...project, role: 'editor' }} onChanged={vi.fn()} />)
  expect(screen.getByText('Only workspace administrators can import or export content.')).toBeTruthy()
  expect(screen.queryByLabelText('Workspace ZIP archive')).toBeNull()
  expect(rest).not.toHaveBeenCalled()
})

test('the destination field editor updates the pipeline schema and clears the review', async () => {
  render(<Migration project={project} onChanged={vi.fn()} />)
  await validate()
  fireEvent.click(screen.getByRole('button', { name: 'Customize destination schemas' }))
  expect(screen.queryByRole('button', { name: 'Import reviewed archive' })).toBeNull()
  fireEvent.change(screen.getByLabelText('Field name title'), { target: { value: 'headline' } })
  fireEvent.click(screen.getByRole('button', { name: 'Validate import' }))
  await screen.findByRole('heading', { name: 'Validation passed — review import' })
  const calls = vi.mocked(rest).mock.calls
  const pipeline = JSON.parse((calls[calls.length - 1][2] as FormData).get('pipeline') as string)
  expect(pipeline.schemas.article.fields).toEqual([{ name: 'headline', type: 'text' }])
})
