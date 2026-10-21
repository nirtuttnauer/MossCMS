import * as DialogPrimitive from '@radix-ui/react-dialog'
import { useRef, type ReactNode } from 'react'
import { X } from 'lucide-react'
import { cn } from '../../lib/utils'

export function Dialog({ title, open, onClose, children, wide }: { title: string; open: boolean; onClose: () => void; children: ReactNode; wide?: boolean }) {
  const opener = useRef<HTMLElement | null>(null)
  return <DialogPrimitive.Root open={open} onOpenChange={value => { if (!value) onClose() }}><DialogPrimitive.Portal><DialogPrimitive.Overlay className="modal-backdrop" /><DialogPrimitive.Content className={cn('entry-modal', wide && 'entry-modal-wide')} aria-describedby={undefined} onOpenAutoFocus={() => {
    opener.current = document.activeElement instanceof HTMLElement && document.activeElement !== document.body ? document.activeElement : null
  }} onCloseAutoFocus={event => {
    const target = opener.current
    if (target?.isConnected && !target.matches(':disabled, [aria-disabled="true"]') && !target.closest('[hidden], [inert]')) {
      event.preventDefault()
      target.focus()
    }
  }}><div className="modal-heading"><DialogPrimitive.Title>{title}</DialogPrimitive.Title><DialogPrimitive.Close className="modal-close" aria-label="Close dialog"><X size={18} aria-hidden="true" /></DialogPrimitive.Close></div>{children}</DialogPrimitive.Content></DialogPrimitive.Portal></DialogPrimitive.Root>
}
