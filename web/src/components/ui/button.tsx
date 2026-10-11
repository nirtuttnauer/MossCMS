import type { ButtonHTMLAttributes } from 'react'
import { cn } from '../../lib/utils'

type Props = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'default' | 'ghost' | 'outline'; size?: 'default' | 'sm' | 'icon' }
export function Button({ className, variant = 'default', size = 'default', ...props }: Props) {
  return <button className={cn('button', `button-${variant}`, size !== 'default' && `button-${size}`, className)} {...props} />
}
