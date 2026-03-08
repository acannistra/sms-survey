import { useQuery } from '@tanstack/react-query'
import { listSurveys } from '@/api/client'
import type { SurveyListResponse } from '@/api/types'

export function useSurveys() {
  return useQuery<SurveyListResponse, Error>({
    queryKey: ['surveys'],
    queryFn: listSurveys,
  })
}
