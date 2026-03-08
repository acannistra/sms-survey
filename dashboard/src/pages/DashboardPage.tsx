import { useState, useRef } from 'react'
import { useSurveys } from '@/hooks/useSurveys'
import { useSurveyStats } from '@/hooks/useSurveyStats'
import { useSurveyFunnel } from '@/hooks/useSurveyFunnel'
import { defaultStartDate, defaultEndDate } from '@/lib/dateUtils'
import { SurveySelectorBar } from '@/components/SurveySelectorBar'
import { StatsGrid } from '@/components/StatsGrid'
import { FunnelChart } from '@/components/FunnelChart'
import { StartWordTable } from '@/components/StartWordTable'
import { ExportPanel } from '@/components/ExportPanel'
import { LastUpdated } from '@/components/LastUpdated'
import { DateRangePicker } from '@/components/DateRangePicker'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'

export function DashboardPage() {
  const [selectedSurveyId, setSelectedSurveyId] = useState<string | null>(null)
  const [startDate, setStartDate] = useState<Date | null>(defaultStartDate())
  const [endDate, setEndDate] = useState<Date | null>(defaultEndDate())
  const lastUpdatedAt = useRef<Date | null>(null)

  const { data: surveyList, isLoading: surveysLoading } = useSurveys()

  const {
    data: stats,
    isLoading: statsLoading,
    isFetching: statsFetching,
    refetch: refetchStats,
    dataUpdatedAt: statsUpdatedAt,
  } = useSurveyStats(selectedSurveyId, startDate, endDate)

  const {
    data: funnel,
    isLoading: funnelLoading,
    refetch: refetchFunnel,
  } = useSurveyFunnel(selectedSurveyId, startDate, endDate)

  if (statsUpdatedAt) {
    lastUpdatedAt.current = new Date(statsUpdatedAt)
  }

  function handleRefresh() {
    void refetchStats()
    void refetchFunnel()
  }

  function handleDateRangeChange(start: Date | null, end: Date | null) {
    setStartDate(start)
    setEndDate(end)
  }

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="border-b border-slate-200 bg-white px-6 py-4">
        <div className="mx-auto max-w-7xl flex items-center justify-between">
          <h1 className="text-xl font-semibold text-slate-900">Survey Dashboard</h1>
          <LastUpdated
            updatedAt={lastUpdatedAt.current}
            onRefresh={handleRefresh}
            isRefreshing={statsFetching}
          />
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 py-8 space-y-8">
        {/* Survey selector + date range */}
        <div className="flex flex-col gap-4">
          <div className="flex items-center justify-between flex-wrap gap-4">
            <SurveySelectorBar
              surveys={surveyList?.surveys ?? []}
              selectedId={selectedSurveyId}
              onChange={setSelectedSurveyId}
              isLoading={surveysLoading}
            />
            {selectedSurveyId && (
              <ExportPanel
                surveyId={selectedSurveyId}
                startDate={startDate}
                endDate={endDate}
              />
            )}
          </div>
          <DateRangePicker
            startDate={startDate}
            endDate={endDate}
            onChange={handleDateRangeChange}
          />
        </div>

        {!selectedSurveyId && (
          <p className="text-slate-500">Select a survey above to view statistics.</p>
        )}

        {/* Stats grid */}
        {selectedSurveyId && (
          <>
            {statsLoading ? (
              <p className="text-slate-400 text-sm">Loading statistics…</p>
            ) : stats ? (
              <StatsGrid stats={stats} />
            ) : null}

            {/* Funnel */}
            <Card>
              <CardHeader>
                <CardTitle>Step Funnel</CardTitle>
              </CardHeader>
              <CardContent>
                {funnelLoading ? (
                  <p className="text-slate-400 text-sm">Loading funnel…</p>
                ) : funnel ? (
                  <FunnelChart funnel={funnel.funnel} />
                ) : null}
              </CardContent>
            </Card>

            {/* Start words */}
            <Card>
              <CardHeader>
                <CardTitle>Start Words</CardTitle>
              </CardHeader>
              <CardContent>
                {funnelLoading ? (
                  <p className="text-slate-400 text-sm">Loading…</p>
                ) : funnel ? (
                  <StartWordTable startWords={funnel.start_words} />
                ) : null}
              </CardContent>
            </Card>
          </>
        )}
      </main>
    </div>
  )
}
