"""Pydantic schemas for dashboard API endpoints.

This module defines request/response schemas for the dashboard API,
which provides survey statistics, funnel analysis, and data export.
"""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class SurveyListItem(BaseModel):
    survey_id: str
    name: str
    description: str
    version: str
    start_words: list[str]


class SurveyListResponse(BaseModel):
    surveys: list[SurveyListItem]


class SurveyStatsResponse(BaseModel):
    survey_id: str
    sessions_started: int
    consents_given: int
    sessions_completed: int
    unique_participants: int
    active_last_48h: int
    opt_outs: int
    avg_completion_pct: float


class StepFunnelItem(BaseModel):
    step_id: str
    step_index: int
    step_type: str
    response_count: int
    drop_off_count: int


class StartWordItem(BaseModel):
    word: str
    count: int


class SurveyFunnelResponse(BaseModel):
    survey_id: str
    funnel: list[StepFunnelItem]
    start_words: list[StartWordItem]


class ExportRow(BaseModel):
    session_id: int
    phone_hash_prefix: str  # first 12 chars only — NEVER the full hash
    survey_id: str
    started_at: datetime
    completed_at: Optional[datetime]
    consent_given: bool
    context: dict
