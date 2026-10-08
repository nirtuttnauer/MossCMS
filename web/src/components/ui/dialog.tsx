import * as DialogPrimitive from '@radix-ui/react-dialog'
import type { ReactNode } from 'react'
import { cn } from '../../lib/utils'

export function Dialog({ title, open, onClose, children, wide }: { title: string; open: boolean; onClose: () => void; children: ReactNode; wide?: boolean }) {
  return <DialogPrimitive.Root open={open} onOpenChange={value => { if (!value) onClose() }}><DialogPrimitive.Portal><DialogPrimitive.Overlay className="modal-backdrop" /><DialogPrimitive.Content className={cn('entry-modal', wide && 'entry-modal-wide')} aria-describedby={undefined}><div className="modal-heading"><DialogPrimitive.Title>{title}</DialogPrimitive.Title><DialogPrimitive.Close className="modal-close" aria-label="Close dialog">×</DialogPrimitive.Close></div>{children}</DialogPrimitive.Content></DialogPrimitive.Portal></DialogPrimitive.Root>
}
