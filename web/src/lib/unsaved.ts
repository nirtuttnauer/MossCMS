import { useLayoutEffect, useRef } from 'react'
const pending = new Set<symbol>()
export function confirmNavigation() {
  return pending.size === 0 || window.confirm('Discard unsaved changes? Your saved draft and live content will be kept.')
}
export function useUnsavedChanges(dirty: boolean) {
  const token = useRef(Symbol('editor'))
  useLayoutEffect(() => {
    if (!dirty) return
    const id = token.current
    pending.add(id)
    const unload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', unload)
    return () => { pending.delete(id); window.removeEventListener('beforeunload', unload) }
  }, [dirty])
  return () => !dirty || window.confirm('Discard unsaved changes? Your saved draft and live content will be kept.')
}
