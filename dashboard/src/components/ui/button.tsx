import { cn } from '@/lib/utils'

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'default' | 'outline' | 'ghost'
  size?: 'sm' | 'md'
}

export function Button({
  className,
  variant = 'default',
  size = 'md',
  ...props
}: ButtonProps) {
  return (
    <button
      className={cn(
        'inline-flex items-center justify-center rounded-md font-medium transition-colors',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-500',
        'disabled:opacity-50 disabled:pointer-events-none',
        variant === 'default' && 'bg-slate-900 text-white hover:bg-slate-700',
        variant === 'outline' &&
          'border border-slate-300 bg-white text-slate-900 hover:bg-slate-50',
        variant === 'ghost' && 'text-slate-700 hover:bg-slate-100',
        size === 'md' && 'h-9 px-4 py-2 text-sm',
        size === 'sm' && 'h-7 px-3 text-xs',
        className,
      )}
      {...props}
    />
  )
}
