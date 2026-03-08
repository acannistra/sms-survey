import { Button } from '@/components/ui/button'

interface LastUpdatedProps {
  updatedAt: Date | null
  onRefresh: () => void
  isRefreshing?: boolean
}

export function LastUpdated({ updatedAt, onRefresh, isRefreshing }: LastUpdatedProps) {
  const label = updatedAt
    ? `Last updated: ${updatedAt.toLocaleTimeString()}`
    : 'Not yet loaded'

  return (
    <div className="flex items-center gap-3 text-sm text-slate-500">
      <span>{label}</span>
      <Button
        variant="ghost"
        size="sm"
        onClick={onRefresh}
        disabled={isRefreshing}
      >
        {isRefreshing ? 'Refreshing…' : 'Refresh now'}
      </Button>
    </div>
  )
}
