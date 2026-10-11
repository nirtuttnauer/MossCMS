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

test.each([
  ['Heading', '## ', ''],
  ['Bold', '**', '**'],
  ['Italic', '*', '*'],
  ['Bullet list', '- ', ''],
  ['Numbered list', '1. ', ''],
  ['Link', '[', '](https://example.com)'],
  ['Code block', '\n```\n', '\n```\n'],
])('%s wraps the selected text, exits preview and restores selection after the animation frame', (name, before, after) => {
  render(<Editor initialValue="Hello world!" assets={[]} />)
  const input = screen.getByLabelText<HTMLTextAreaElement>('Body')
  input.setSelectionRange(6, 11)
  fireEvent.click(screen.getByRole('button', { name: 'Preview Markdown' }))
  expect(input.hidden).toBe(true)

  const button = screen.getByRole('button', { name })
  button.focus()
  fireEvent.click(button)

  expect(input.value).toBe(`Hello ${before}world${after}!`)
  expect(input.hidden).toBe(false)
  expect(document.activeElement).toBe(button)
  expect(frames).toHaveLength(1)
  act(() => frames[0](0))
  expect(document.activeElement).toBe(input)
  expect([input.selectionStart, input.selectionEnd]).toEqual([6 + before.length, 11 + before.length])
})

test('inserts the text placeholder at a collapsed caret', () => {
  render(<Editor initialValue="left right" assets={[]} />)
  const input = screen.getByLabelText<HTMLTextAreaElement>('Body')
  input.setSelectionRange(4, 4)

  fireEvent.click(screen.getByRole('button', { name: 'Bold' }))

  expect(input.value).toBe('left**text** right')
  expect(frames).toHaveLength(1)
  act(() => frames[0](0))
  expect(document.activeElement).toBe(input)
  expect([input.selectionStart, input.selectionEnd]).toEqual([6, 10])
})

test('replaces selected text with a durable image ID and sanitized alt text', () => {
  render(<Editor initialValue="Start old end" assets={[]} editable />)
  const input = screen.getByLabelText<HTMLTextAreaElement>('Body')
  const insert = screen.getByRole<HTMLButtonElement>('button', { name: 'Insert image' })
  expect(insert.disabled).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: 'Upload test image' }))
  fireEvent.change(screen.getByLabelText('Image alt text'), { target: { value: '  ' } })
  expect(insert.disabled).toBe(true)
  fireEvent.change(screen.getByLabelText('Image alt text'), { target: { value: '[A]\\B]' } })
  expect(insert.disabled).toBe(false)
  input.setSelectionRange(6, 9)
  fireEvent.click(screen.getByRole('button', { name: 'Preview Markdown' }))

  fireEvent.click(insert)

  expect(input.hidden).toBe(false)
  expect(input.value).toBe('Start ![AB](asset:image) end')
  expect(input.value).not.toContain(uploadedAsset.url)
  expect(frames).toHaveLength(1)
  act(() => frames[0](0))
  expect(document.activeElement).toBe(input)
  expect([input.selectionStart, input.selectionEnd]).toEqual([12, 23])
  fireEvent.click(screen.getByRole('button', { name: 'Preview Markdown' }))
  expect(screen.getByAltText('AB').getAttribute('src')).toBe(uploadedAsset.url)

  fireEvent.click(screen.getByRole('button', { name: 'Clear test asset' }))
  expect(screen.getByLabelText<HTMLInputElement>('Image asset').value).toBe('')
  expect(insert.disabled).toBe(true)
})

test('validation errors return to the editor and preserve its accessible field props', () => {
  const view = render(<Editor initialValue="Saved content" assets={[]} required id="body" />)
  const input = screen.getByLabelText<HTMLTextAreaElement>('Body *')
  fireEvent.click(screen.getByRole('button', { name: 'Preview Markdown' }))
  expect(input.hidden).toBe(true)

  view.rerender(<Editor initialValue="Saved content" assets={[]} required id="body" error="Body is invalid" />)

  expect(input.hidden).toBe(false)
  expect(input.value).toBe('Saved content')
  expect(input.required).toBe(true)
  expect(input.id).toBe('body')
  expect(input.dir).toBe('auto')
  expect(input.getAttribute('aria-invalid')).toBe('true')
  expect(input.getAttribute('aria-describedby')).toBe('error-body')
  expect(screen.getByRole('button', { name: 'Preview Markdown' }).getAttribute('aria-pressed')).toBe('false')
})

test('project changes clear image selection, alt text and uploaded preview assets while retaining content and provided assets', () => {
  const initialValue = '![Existing](asset:existing)\n\n![Uploaded](asset:image)'
  const assets: Asset[] = [{ id: 'existing', name: 'existing.png', mime: 'image/png', size: 100, url: '/media/existing' }]
  const view = render(<Editor initialValue={initialValue} assets={assets} editable projectId="first" />)
  fireEvent.click(screen.getByRole('button', { name: 'Upload test image' }))
  fireEvent.change(screen.getByLabelText('Image alt text'), { target: { value: 'Cover' } })
  fireEvent.click(screen.getByRole('button', { name: 'Preview Markdown' }))
  expect(screen.getByAltText('Existing').getAttribute('src')).toBe('/media/existing')
  expect(screen.getByAltText('Uploaded').getAttribute('src')).toBe(uploadedAsset.url)

  view.rerender(<Editor initialValue={initialValue} assets={assets} editable projectId="second" />)

  expect(screen.getByLabelText<HTMLInputElement>('Image asset').value).toBe('')
  expect(screen.getByLabelText<HTMLInputElement>('Image alt text').value).toBe('')
  expect(screen.getByRole<HTMLButtonElement>('button', { name: 'Insert image' }).disabled).toBe(true)
  expect(screen.getByLabelText<HTMLTextAreaElement>('Body').value).toBe(initialValue)
  expect(screen.getByLabelText<HTMLTextAreaElement>('Body').hidden).toBe(true)
  expect(screen.getByAltText('Existing').getAttribute('src')).toBe('/media/existing')
  expect(screen.queryByAltText('Uploaded')).toBeNull()
  expect(screen.getByRole('img', { name: 'Uploaded' }).textContent).toBe('[Image unavailable: Uploaded]')
})
