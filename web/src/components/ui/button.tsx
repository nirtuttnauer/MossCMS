import type { ButtonHTMLAttributes } from 'react'
import { cn } from '../../lib/utils'

type Props = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'default' | 'ghost' | 'outline' }
export function Button({ className, variant = 'default', ...props }: Props) {
  return <button className={cn('button', `button-${variant}`, className)} {...props} />
}
