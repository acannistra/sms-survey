import type { SurveyListResponse, SurveyStatsResponse, SurveyFunnelResponse } from './types'

const BASE = '/api/dashboard'

async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${res.statusText}`)
  }
  return res.json() as Promise<T>
}

function dateParam(d: Date | null | undefined): string {
  return d ? d.toISOString() : ''
}

export function listSurveys(): Promise<SurveyListResponse> {
  return apiFetch<SurveyListResponse>('/surveys')
}

export function getSurveyStats(
  surveyId: string,
  startDate?: Date | null,
  endDate?: Date | null,
): Promise<SurveyStatsResponse> {
  const params = new URLSearchParams()
  if (startDate) params.set('start_date', dateParam(startDate))
  if (endDate) params.set('end_date', dateParam(endDate))
  const qs = params.toString() ? `?${params.toString()}` : ''
  return apiFetch<SurveyStatsResponse>(`/surveys/${encodeURIComponent(surveyId)}/stats${qs}`)
}

export function getSurveyFunnel(
  surveyId: string,
  startDate?: Date | null,
  endDate?: Date | null,
): Promise<SurveyFunnelResponse> {
  const params = new URLSearchParams()
  if (startDate) params.set('start_date', dateParam(startDate))
  if (endDate) params.set('end_date', dateParam(endDate))
  const qs = params.toString() ? `?${params.toString()}` : ''
  return apiFetch<SurveyFunnelResponse>(`/surveys/${encodeURIComponent(surveyId)}/funnel${qs}`)
}

/** Returns a URL string for direct download — use window.location.href, NOT fetch(). */
export function exportUrl(
  surveyId: string,
  format: 'csv' | 'json' | 'xlsx',
  startDate?: Date | null,
  endDate?: Date | null,
): string {
  const params = new URLSearchParams({ format })
  if (startDate) params.set('start_date', dateParam(startDate))
  if (endDate) params.set('end_date', dateParam(endDate))
  return `${BASE}/surveys/${encodeURIComponent(surveyId)}/export?${params.toString()}`
}
