import { Badge } from '@/components/ui/badge'
import type { StartWordItem } from '@/api/types'

interface StartWordTableProps {
  startWords: StartWordItem[]
}

export function StartWordTable({ startWords }: StartWordTableProps) {
  if (startWords.length === 0) {
    return (
      <p className="text-sm text-slate-500 py-2">No start word data available yet.</p>
    )
  }

  const total = startWords.reduce((sum, w) => sum + w.count, 0)

  return (
    <div className="flex flex-wrap gap-2">
      {startWords.map((item) => {
        const pct = total > 0 ? ((item.count / total) * 100).toFixed(1) : '0.0'
        return (
          <div
            key={item.word}
            className="flex items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5"
          >
            <Badge variant="secondary">{item.word}</Badge>
            <span className="text-xs font-medium tabular-nums text-slate-700">
              {item.count}
            </span>
            <span className="text-xs text-slate-400">({pct}%)</span>
          </div>
        )
      })}
    </div>
  )
}
