import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import type { SurveyStatsResponse } from '@/api/types'

interface StatCardProps {
  title: string
  value: string | number
}

function StatCard({ title, value }: StatCardProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-2xl font-bold text-slate-900">{value}</p>
      </CardContent>
    </Card>
  )
}

interface StatsGridProps {
  stats: SurveyStatsResponse
}

export function StatsGrid({ stats }: StatsGridProps) {
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
      <StatCard title="Sessions Started" value={stats.sessions_started} />
      <StatCard title="Consents Given" value={stats.consents_given} />
      <StatCard title="Completed" value={stats.sessions_completed} />
      <StatCard title="Unique Participants" value={stats.unique_participants} />
      <StatCard title="Active (last 48h)" value={stats.active_last_48h} />
      <StatCard title="Opt-outs (global)" value={stats.opt_outs} />
      <StatCard
        title="Completion Rate"
        value={`${stats.avg_completion_pct.toFixed(1)}%`}
      />
    </div>
  )
}
