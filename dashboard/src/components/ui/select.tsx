import { cn } from '@/lib/utils'

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string
}

export function Select({ className, label, id, children, ...props }: SelectProps) {
  return (
    <div className="flex flex-col gap-1">
      {label && (
        <label htmlFor={id} className="text-xs font-medium text-slate-600">
          {label}
        </label>
      )}
      <select
        id={id}
        className={cn(
          'h-9 rounded-md border border-slate-300 bg-white px-3 py-1 text-sm text-slate-900',
          'focus:outline-none focus:ring-2 focus:ring-slate-400',
          'disabled:opacity-50',
          className,
        )}
        {...props}
      >
        {children}
      </select>
    </div>
  )
}
