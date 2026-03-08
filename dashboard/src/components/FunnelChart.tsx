import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'
import type { StepFunnelItem } from '@/api/types'

interface FunnelChartProps {
  funnel: StepFunnelItem[]
}

export function FunnelChart({ funnel }: FunnelChartProps) {
  if (funnel.length === 0) {
    return (
      <p className="text-sm text-slate-500 py-4">No funnel data available yet.</p>
    )
  }

  return (
    <div className="space-y-6">
      {/* Horizontal bar chart */}
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={funnel}
            layout="vertical"
            margin={{ top: 4, right: 24, left: 8, bottom: 4 }}
          >
            <XAxis type="number" tick={{ fontSize: 12 }} />
            <YAxis
              type="category"
              dataKey="step_id"
              width={120}
              tick={{ fontSize: 11 }}
            />
            <Tooltip
              formatter={(value, name) => [
                value,
                name === 'response_count' ? 'Responses' : 'Drop-offs',
              ]}
            />
            <Bar dataKey="response_count" name="response_count" radius={[0, 4, 4, 0]}>
              {funnel.map((entry) => (
                <Cell
                  key={entry.step_id}
                  fill={entry.step_type === 'terminal' ? '#94a3b8' : '#3b82f6'}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Accessible table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm text-left">
          <thead>
            <tr className="border-b border-slate-200">
              <th className="pb-2 pr-4 font-medium text-slate-600">Step</th>
              <th className="pb-2 pr-4 font-medium text-slate-600 text-right">Responses</th>
              <th className="pb-2 pr-4 font-medium text-slate-600 text-right">Drop-offs</th>
              <th className="pb-2 font-medium text-slate-600">Type</th>
            </tr>
          </thead>
          <tbody>
            {funnel.map((item) => (
              <tr key={item.step_id} className="border-b border-slate-100 hover:bg-slate-50">
                <td className="py-2 pr-4 font-mono text-xs text-slate-700">{item.step_id}</td>
                <td className="py-2 pr-4 text-right tabular-nums">{item.response_count}</td>
                <td className="py-2 pr-4 text-right tabular-nums text-red-500">
                  {item.drop_off_count > 0 ? `-${item.drop_off_count}` : '—'}
                </td>
                <td className="py-2">
                  <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">
                    {item.step_type}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
