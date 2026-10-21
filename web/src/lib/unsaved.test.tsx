import { StrictMode } from 'react'
import { cleanup, fireEvent, render, renderHook, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { confirmNavigation, useUnsavedChanges } from './unsaved'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function Editor({ dirty }: { dirty: boolean }) {
  const close = useUnsavedChanges(dirty)
  return <button onClick={() => close()}>Close</button>
}

test('clean form leaves without confirmation; dirty form protects unload and navigation', () => {
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
  const view = render(<Editor dirty={false} />)
  expect(confirmNavigation()).toBe(true)
  fireEvent.click(screen.getByText('Close'))
  expect(confirm).not.toHaveBeenCalled()
  view.rerender(<Editor dirty />)
  expect(confirmNavigation()).toBe(false)
  const event = new Event('beforeunload', { cancelable: true })
  Object.defineProperty(event, 'returnValue', { value: undefined, writable: true })
  window.dispatchEvent(event)
  expect(event.defaultPrevented).toBe(true)
  expect(event.returnValue).toBe('')
  view.unmount()
  expect(confirmNavigation()).toBe(true)
})

test('each dirty editor protects navigation until it unmounts independently', () => {
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
  const first = renderHook(() => useUnsavedChanges(true))
  const second = renderHook(() => useUnsavedChanges(true))

  expect(confirmNavigation()).toBe(false)
  first.unmount()
  expect(confirmNavigation()).toBe(false)
  const event = new Event('beforeunload', { cancelable: true })
  window.dispatchEvent(event)
  expect(event.defaultPrevented).toBe(true)

  second.unmount()
  expect(confirmNavigation()).toBe(true)
  expect(confirm).toHaveBeenCalledTimes(2)
  const afterUnmount = new Event('beforeunload', { cancelable: true })
  window.dispatchEvent(afterUnmount)
  expect(afterUnmount.defaultPrevented).toBe(false)
})

test('cleaning one editor leaves another dirty editor protected', () => {
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
  const first = renderHook(({ dirty }) => useUnsavedChanges(dirty), { initialProps: { dirty: true } })
  const second = renderHook(({ dirty }) => useUnsavedChanges(dirty), { initialProps: { dirty: true } })

  first.rerender({ dirty: false })
  expect(first.result.current()).toBe(true)
  expect(confirm).not.toHaveBeenCalled()
  expect(confirmNavigation()).toBe(false)
  const event = new Event('beforeunload', { cancelable: true })
  window.dispatchEvent(event)
  expect(event.defaultPrevented).toBe(true)

  second.rerender({ dirty: false })
  expect(confirmNavigation()).toBe(true)
  expect(confirm).toHaveBeenCalledOnce()
  const afterClean = new Event('beforeunload', { cancelable: true })
  window.dispatchEvent(afterClean)
  expect(afterClean.defaultPrevented).toBe(false)
})

test('local guards only confirm their editor while global navigation uses any dirty editor', () => {
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
  const clean = renderHook(() => useUnsavedChanges(false))
  const dirty = renderHook(() => useUnsavedChanges(true))

  expect(clean.result.current()).toBe(true)
  expect(confirm).not.toHaveBeenCalled()
  expect(dirty.result.current()).toBe(false)
  expect(confirmNavigation()).toBe(false)
  confirm.mockReturnValue(true)
  expect(dirty.result.current()).toBe(true)
  expect(confirmNavigation()).toBe(true)
  expect(confirm).toHaveBeenCalledTimes(4)
  for (const [message] of confirm.mock.calls) {
    expect(message).toBe('Discard unsaved changes? Your saved draft and live content will be kept.')
  }
})

test('StrictMode cleanup leaves no pending editors or unload listeners', () => {
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
  const addListener = vi.spyOn(window, 'addEventListener')
  const removeListener = vi.spyOn(window, 'removeEventListener')
  const view = renderHook(() => useUnsavedChanges(true), { wrapper: StrictMode })

  expect(confirmNavigation()).toBe(false)
  const event = new Event('beforeunload', { cancelable: true })
  window.dispatchEvent(event)
  expect(event.defaultPrevented).toBe(true)
  view.unmount()
  expect(confirmNavigation()).toBe(true)
  expect(confirm).toHaveBeenCalledOnce()
  const afterUnmount = new Event('beforeunload', { cancelable: true })
  window.dispatchEvent(afterUnmount)
  expect(afterUnmount.defaultPrevented).toBe(false)
  const added = addListener.mock.calls.filter(([type]) => type === 'beforeunload').map(([, listener]) => listener)
  const removed = removeListener.mock.calls.filter(([type]) => type === 'beforeunload').map(([, listener]) => listener)
  expect(added).toHaveLength(2)
  expect(removed).toEqual(added)
})

test('configuration guards use their own recovery message without changing editor prompts', () => {
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
  const settings = renderHook(() => useUnsavedChanges(true, 'Discard unsaved settings?'))
  expect(confirmNavigation()).toBe(false)
  expect(confirm).toHaveBeenLastCalledWith('Discard unsaved settings?')
  settings.unmount()
  renderHook(() => useUnsavedChanges(true))
  expect(confirmNavigation()).toBe(false)
  expect(confirm).toHaveBeenLastCalledWith('Discard unsaved changes? Your saved draft and live content will be kept.')
})
