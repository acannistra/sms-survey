import { Button } from '@/components/ui/button'
import { subDays, subMonths, format } from 'date-fns'

interface DateRangePickerProps {
  startDate: Date | null
  endDate: Date | null
  onChange: (start: Date | null, end: Date | null) => void
}

const PRESETS = [
  { label: '7d', days: 7 },
  { label: '30d', days: 30 },
  { label: '90d', days: 90 },
  { label: '6mo', months: 6 },
]

function toInputValue(date: Date | null): string {
  return date ? format(date, 'yyyy-MM-dd') : ''
}

function isPresetActive(days: number | undefined, months: number | undefined, start: Date | null, end: Date | null): boolean {
  if (!start || !end) return false
  const now = new Date()
  const expected = days ? subDays(now, days) : subMonths(now, months!)
  // Compare dates at day granularity
  return (
    format(start, 'yyyy-MM-dd') === format(expected, 'yyyy-MM-dd') &&
    format(end, 'yyyy-MM-dd') === format(now, 'yyyy-MM-dd')
  )
}

export function DateRangePicker({ startDate, endDate, onChange }: DateRangePickerProps) {
  function applyPreset(days?: number, months?: number) {
    const end = new Date()
    const start = days ? subDays(end, days) : subMonths(end, months!)
    onChange(start, end)
  }

  function handleStartChange(e: React.ChangeEvent<HTMLInputElement>) {
    const val = e.target.value
    onChange(val ? new Date(val + 'T00:00:00') : null, endDate)
  }

  function handleEndChange(e: React.ChangeEvent<HTMLInputElement>) {
    const val = e.target.value
    onChange(startDate, val ? new Date(val + 'T23:59:59') : null)
  }

  return (
    <div className="flex items-center gap-2 flex-wrap">
      {/* Preset buttons */}
      {PRESETS.map((p) => {
        const active = isPresetActive(p.days, p.months, startDate, endDate)
        return (
          <Button
            key={p.label}
            size="sm"
            variant={active ? 'default' : 'outline'}
            onClick={() => applyPreset(p.days, p.months)}
          >
            {p.label}
          </Button>
        )
      })}

      <Button
        size="sm"
        variant={!startDate && !endDate ? 'default' : 'outline'}
        onClick={() => onChange(null, null)}
      >
        All time
      </Button>

      {/* Divider */}
      <span className="text-slate-300 select-none hidden sm:inline">|</span>

      {/* Manual date inputs */}
      <div className="flex items-center gap-1 text-sm text-slate-600">
        <input
          type="date"
          value={toInputValue(startDate)}
          max={toInputValue(endDate)}
          onChange={handleStartChange}
          className="border border-slate-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
        />
        <span className="text-slate-400">–</span>
        <input
          type="date"
          value={toInputValue(endDate)}
          min={toInputValue(startDate)}
          onChange={handleEndChange}
          className="border border-slate-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
        />
      </div>
    </div>
  )
}
