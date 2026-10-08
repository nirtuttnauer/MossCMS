import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { confirmNavigation, useUnsavedChanges } from './unsaved'
afterEach(() => {cleanup(); vi.restoreAllMocks()})
function Editor({dirty}: {dirty:boolean}) {const close=useUnsavedChanges(dirty); return <button onClick={() => close()}>Close</button>}
test('clean form leaves without confirmation; dirty form protects unload and navigation', () => {
  const confirm=vi.spyOn(window,'confirm').mockReturnValue(false)
  const view=render(<Editor dirty={false} />)
  expect(confirmNavigation()).toBe(true)
  fireEvent.click(screen.getByText('Close'))
  expect(confirm).not.toHaveBeenCalled()
  view.rerender(<Editor dirty />)
  expect(confirmNavigation()).toBe(false)
  const event = new Event('beforeunload',{cancelable:true})
  window.dispatchEvent(event)
  expect(event.defaultPrevented).toBe(true)
  view.unmount()
  expect(confirmNavigation()).toBe(true)
})
