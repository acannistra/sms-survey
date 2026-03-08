import { useQuery } from '@tanstack/react-query'
import { getSurveyFunnel } from '@/api/client'
import type { SurveyFunnelResponse } from '@/api/types'

export function useSurveyFunnel(
  surveyId: string | null,
  startDate?: Date | null,
  endDate?: Date | null,
) {
  return useQuery<SurveyFunnelResponse, Error>({
    queryKey: ['surveyFunnel', surveyId, startDate?.toISOString(), endDate?.toISOString()],
    queryFn: () => getSurveyFunnel(surveyId!, startDate, endDate),
    enabled: !!surveyId,
    refetchInterval: 60000,
  })
}
