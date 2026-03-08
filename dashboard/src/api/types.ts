export interface SurveyListItem {
  survey_id: string
  name: string
  description: string
  version: string
  start_words: string[]
}

export interface SurveyListResponse {
  surveys: SurveyListItem[]
}

export interface SurveyStatsResponse {
  survey_id: string
  sessions_started: number
  consents_given: number
  sessions_completed: number
  unique_participants: number
  active_last_48h: number
  opt_outs: number
  avg_completion_pct: number
}

export interface StepFunnelItem {
  step_id: string
  step_index: number
  step_type: string
  response_count: number
  drop_off_count: number
}

export interface StartWordItem {
  word: string
  count: number
}

export interface SurveyFunnelResponse {
  survey_id: string
  funnel: StepFunnelItem[]
  start_words: StartWordItem[]
}
