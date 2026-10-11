import { useState } from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Dialog } from './dialog'

afterEach(cleanup)

function Example() {
  const [open, setOpen] = useState(false), [showOpener, setShowOpener] = useState(true), [disabled, setDisabled] = useState(false)
  return <>
    {showOpener && <button disabled={disabled} onClick={() => setOpen(true)}>Open example</button>}
    <Dialog title="Example dialog" open={open} onClose={() => setOpen(false)}>
      <button onClick={() => setOpen(false)}>Cancel</button>
      <button onClick={() => setShowOpener(false)}>Remove opener</button>
      <button onClick={() => setDisabled(true)}>Disable opener</button>
    </Dialog>
  </>
}

async function openExample() {
  const opener = screen.getByRole('button', { name: 'Open example' })
  opener.focus()
  fireEvent.click(opener)
  await screen.findByRole('dialog', { name: 'Example dialog' })
  await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Close dialog' })))
  return opener
}

describe('controlled dialogs without a Radix trigger', () => {
  it.each(['Escape', 'Cancel'])('restores keyboard focus to the opening control after %s', async action => {
    render(<Example />)
    const opener = await openExample()
    if (action === 'Escape') fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
    else fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    await waitFor(() => expect(document.activeElement).toBe(opener))
  })

  it.each(['Remove opener', 'Disable opener'])('does not focus a stale or disabled opening control after %s', async action => {
    render(<Example />)
    const opener = await openExample()
    const focus = vi.spyOn(opener, 'focus')
    fireEvent.click(screen.getByRole('button', { name: action }))
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    // Radix dispatches close-auto-focus after its unmount cleanup.
    await new Promise(resolve => setTimeout(resolve, 10))
    expect(focus).not.toHaveBeenCalled()
    expect(document.activeElement?.isConnected).toBe(true)
  })
})
