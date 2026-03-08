import { cn } from '@/lib/utils'

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: 'default' | 'secondary' | 'outline'
}

export function Badge({ className, variant = 'default', ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold',
        variant === 'default' && 'bg-slate-900 text-white',
        variant === 'secondary' && 'bg-slate-100 text-slate-900',
        variant === 'outline' && 'border border-slate-200 text-slate-700',
        className,
      )}
      {...props}
    />
  )
}
