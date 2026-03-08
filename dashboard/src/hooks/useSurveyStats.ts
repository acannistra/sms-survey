import { useQuery } from '@tanstack/react-query'
import { getSurveyStats } from '@/api/client'
import type { SurveyStatsResponse } from '@/api/types'

export function useSurveyStats(
  surveyId: string | null,
  startDate?: Date | null,
  endDate?: Date | null,
) {
  return useQuery<SurveyStatsResponse, Error>({
    queryKey: ['surveyStats', surveyId, startDate?.toISOString(), endDate?.toISOString()],
    queryFn: () => getSurveyStats(surveyId!, startDate, endDate),
    enabled: !!surveyId,
    refetchInterval: 60000, // auto-refresh every 60 seconds
  })
}
