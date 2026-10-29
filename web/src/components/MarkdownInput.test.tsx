import { useState, type ComponentProps } from 'react'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { MarkdownInput } from './MarkdownInput'
import type { AssetPicker } from './AssetPicker'
import type { Asset } from '../lib/api'

const uploadedAsset: Asset = {
  id: 'image',
  name: 'cover.png',
  mime: 'image/png',
  size: 100,
  url: 'https://media.example/uploaded?expires=123',
}

vi.mock('./AssetPicker', () => ({
  AssetPicker: ({ label, value, onChange, onUploaded, editable }: ComponentProps<typeof AssetPicker>) => (
    <div>
      <label>
        {label}
        <input value={value} onChange={event => onChange(event.target.value)} />
      </label>
      <button type="button" onClick={() => onChange(null)}>Clear test asset</button>
      {editable && (
        <button type="button" onClick={() => {
          onUploaded?.(uploadedAsset)
          onChange(uploadedAsset.id)
        }}>
          Upload test image
        </button>
      )}
    </div>
  ),
}))

function Editor({
  initialValue = '',
  ...props
}: Omit<ComponentProps<typeof MarkdownInput>, 'label' | 'value' | 'onChange'> & { initialValue?: string }) {
  const [value, setValue] = useState(initialValue)
  return <MarkdownInput label="Body" value={value} onChange={setValue} {...props} />
}

let frames: FrameRequestCallback[]

beforeEach(() => {
  frames = []
  vi.stubGlobal('requestAnimationFrame', vi.fn((callback: FrameRequestCallback) => frames.push(callback)))
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

test('visual formatting updates the markdown string and source mode can wrap a selection', () => {
  render(<Editor initialValue="Hello world!" assets={[]} />)
  fireEvent.click(screen.getByRole('button', { name: 'Bold' }))
  fireEvent.click(screen.getByRole('button', { name: 'Source' }))
  const input = screen.getByLabelText<HTMLTextAreaElement>('Body')
  expect(input.value).toBe('**Hello world!**\n')
  input.setSelectionRange(8, 13)
  fireEvent.click(screen.getByRole('button', { name: 'Italic' }))
  expect(input.value).toBe('**Hello *world*!**\n')
  expect(frames).toHaveLength(1)
  act(() => frames[0](0))
  expect(document.activeElement).toBe(input)
})

test('pasted plain text becomes markdown without another keystroke', () => {
  render(<Editor initialValue="" assets={[]} />)
  const visual = screen.getByRole('group', { name: 'Body visual editor' }).querySelector<HTMLElement>('[role="textbox"]')!
  visual.focus()
  const selection = document.getSelection()!
  const range = document.createRange()
  range.selectNodeContents(visual)
  selection.removeAllRanges()
  selection.addRange(range)
  fireEvent.paste(visual, { clipboardData: { getData: () => 'Pasted line' } })
  fireEvent.click(screen.getByRole('button', { name: 'Source' }))
  expect(screen.getByLabelText<HTMLTextAreaElement>('Body').value).toBe('Pasted line\n')
})

test('inserts a durable image id from either mode and renders it', () => {
  render(<Editor initialValue="Start old end" assets={[]} editable />)
  fireEvent.click(screen.getByRole('button', { name: 'Upload test image' }))
  fireEvent.change(screen.getByLabelText('Image alt text'), { target: { value: '[A]\\B]' } })
  fireEvent.click(screen.getByRole('button', { name: 'Insert image' }))
  expect(screen.getByText('asset:image')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Source' }))
  const input = screen.getByLabelText<HTMLTextAreaElement>('Body')
  expect(input.value).toBe('Start old end\n\n![AB](asset:image)\n')
  expect(input.value).not.toContain(uploadedAsset.url)
  fireEvent.click(screen.getByRole('button', { name: 'Visual' }))
  expect(screen.getByText('asset:image')).toBeTruthy()
})

test('validation errors return to source and preserve accessible field props', () => {
  const view = render(<Editor initialValue="Saved content" assets={[]} required id="body" />)
  view.rerender(<Editor initialValue="Saved content" assets={[]} required id="body" error="Body is invalid" />)
  const input = screen.getByLabelText<HTMLTextAreaElement>('Body *')
  expect(input.hidden).toBe(false)
  expect(input.value).toBe('Saved content')
  expect(input.required).toBe(true)
  expect(input.id).toBe('body')
  expect(input.dir).toBe('auto')
  expect(input.getAttribute('aria-invalid')).toBe('true')
  expect(input.getAttribute('aria-describedby')).toBe('error-body')
  expect(screen.getByRole('button', { name: 'Visual' }).getAttribute('aria-pressed')).toBe('true')
})

test('a visit to visual mode leaves unsupported source unchanged', () => {
  const initialValue = '<div>keep me</div>\n\n:::warning\nstill here'
  render(<Editor initialValue={initialValue} assets={[]} />)
  expect(screen.getByRole('status').textContent).toMatch(/left unchanged/)
  fireEvent.click(screen.getByRole('button', { name: 'Bold' }))
  fireEvent.click(screen.getByRole('button', { name: 'Source' }))
  expect(screen.getByLabelText<HTMLTextAreaElement>('Body').value).toContain('<div>keep me</div>')
  expect(screen.getByLabelText<HTMLTextAreaElement>('Body').value).toContain(':::warning')
})

test('project changes clear image selection while retaining content', () => {
  const initialValue = '![Existing](asset:existing)\n\n![Uploaded](asset:image)\n'
  const assets: Asset[] = [{ id: 'existing', name: 'existing.png', mime: 'image/png', size: 100, url: '/media/existing' }]
  const view = render(<Editor initialValue={initialValue} assets={assets} editable projectId="first" />)
  fireEvent.click(screen.getByRole('button', { name: 'Upload test image' }))
  fireEvent.change(screen.getByLabelText('Image alt text'), { target: { value: 'Cover' } })
  view.rerender(<Editor initialValue={initialValue} assets={assets} editable projectId="second" />)
  expect(screen.getByLabelText<HTMLInputElement>('Image asset').value).toBe('')
  expect(screen.getByLabelText<HTMLInputElement>('Image alt text').value).toBe('')
  expect(screen.getByRole<HTMLButtonElement>('button', { name: 'Insert image' }).disabled).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: 'Source' }))
  expect(screen.getByLabelText<HTMLTextAreaElement>('Body').value).toBe(initialValue)
})
