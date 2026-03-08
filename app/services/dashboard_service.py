"""Dashboard service providing survey statistics, funnel analysis, and export.

This module implements the business logic for the dashboard API endpoints.
All phone hash references are truncated to 12 characters (never the full hash).
"""

from datetime import datetime, timezone, timedelta
from io import BytesIO
from typing import Optional

from sqlalchemy import func, distinct, select
from sqlalchemy.orm import Session

from app.models.session import SurveySession
from app.models.response import SurveyResponse
from app.models.optout import OptOut
from app.schemas.dashboard import (
    SurveyListItem,
    SurveyListResponse,
    SurveyStatsResponse,
    StepFunnelItem,
    StartWordItem,
    SurveyFunnelResponse,
    ExportRow,
)
from app.schemas.survey import QuestionType
from app.services.survey_loader import get_survey_loader, SurveyNotFoundError
from app.logging_config import get_logger

logger = get_logger(__name__)


def get_survey_list() -> SurveyListResponse:
    """Return list of all available surveys with metadata.

    Loads survey definitions from YAML files via the survey loader.

    Returns:
        SurveyListResponse with a list of SurveyListItem
    """
    loader = get_survey_loader()
    survey_ids = loader.list_surveys()

    items: list[SurveyListItem] = []
    for survey_id in survey_ids:
        try:
            survey = loader.load_survey(survey_id)
            items.append(
                SurveyListItem(
                    survey_id=survey.metadata.id,
                    name=survey.metadata.name,
                    description=survey.metadata.description,
                    version=survey.metadata.version,
                    start_words=survey.metadata.start_words,
                )
            )
        except Exception as exc:
            logger.warning(f"Skipping survey '{survey_id}' due to load error: {exc}")

    return SurveyListResponse(surveys=items)


def get_survey_stats(
    db: Session,
    survey_id: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> SurveyStatsResponse:
    """Return aggregate statistics for a single survey.

    Args:
        db: Database session
        survey_id: Survey identifier (must match a YAML file)
        start_date: Optional filter — include sessions started on or after this date
        end_date: Optional filter — include sessions started on or before this date

    Returns:
        SurveyStatsResponse with counts and percentages

    Raises:
        SurveyNotFoundError: If survey_id does not match any YAML file
    """
    # Validate survey exists — raises SurveyNotFoundError if not
    loader = get_survey_loader()
    loader.load_survey(survey_id)

    # Base query filtered by survey_id and optional date range
    base_q = db.query(SurveySession).filter(SurveySession.survey_id == survey_id)

    if start_date is not None:
        base_q = base_q.filter(SurveySession.started_at >= start_date)
    if end_date is not None:
        base_q = base_q.filter(SurveySession.started_at <= end_date)

    sessions_started = base_q.count()

    consents_given = base_q.filter(SurveySession.consent_given.is_(True)).count()

    sessions_completed = base_q.filter(
        SurveySession.completed_at.isnot(None)
    ).count()

    unique_participants = (
        base_q.with_entities(func.count(distinct(SurveySession.phone_hash))).scalar()
        or 0
    )

    cutoff_48h = datetime.now(timezone.utc) - timedelta(hours=48)
    active_last_48h = base_q.filter(
        SurveySession.updated_at >= cutoff_48h
    ).count()

    # Opt-outs are global (no survey_id column on OptOut)
    opt_outs = db.query(OptOut).count()

    avg_completion_pct = (
        round(sessions_completed / consents_given * 100, 2)
        if consents_given > 0
        else 0.0
    )

    return SurveyStatsResponse(
        survey_id=survey_id,
        sessions_started=sessions_started,
        consents_given=consents_given,
        sessions_completed=sessions_completed,
        unique_participants=unique_participants,
        active_last_48h=active_last_48h,
        opt_outs=opt_outs,
        avg_completion_pct=avg_completion_pct,
    )


def get_survey_funnel(
    db: Session,
    survey_id: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> SurveyFunnelResponse:
    """Return step-by-step funnel analysis for a survey.

    Args:
        db: Database session
        survey_id: Survey identifier
        start_date: Optional filter on session started_at
        end_date: Optional filter on session started_at

    Returns:
        SurveyFunnelResponse with funnel and start_word breakdown

    Raises:
        SurveyNotFoundError: If survey_id does not match any YAML file
    """
    # Validate and load survey for canonical step ordering
    loader = get_survey_loader()
    survey = loader.load_survey(survey_id)

    # Build base session subquery for date filtering
    session_q = db.query(SurveySession.id).filter(
        SurveySession.survey_id == survey_id
    )
    if start_date is not None:
        session_q = session_q.filter(SurveySession.started_at >= start_date)
    if end_date is not None:
        session_q = session_q.filter(SurveySession.started_at <= end_date)
    session_ids = [row[0] for row in session_q.all()]

    # Query 1: count valid responses per step_id, excluding __session_start__
    if session_ids:
        step_counts_rows = (
            db.query(SurveyResponse.step_id, func.count(SurveyResponse.id))
            .filter(
                SurveyResponse.session_id.in_(session_ids),
                SurveyResponse.step_id != "__session_start__",
                SurveyResponse.is_valid.is_(True),
            )
            .group_by(SurveyResponse.step_id)
            .all()
        )
    else:
        step_counts_rows = []

    step_counts: dict[str, int] = {row[0]: row[1] for row in step_counts_rows}

    # Build funnel in YAML step order
    funnel_dicts: list[dict] = []
    for idx, step in enumerate(survey.steps):
        funnel_dicts.append(
            {
                "step_id": step.id,
                "step_index": idx,
                "step_type": step.type.value,
                "response_count": step_counts.get(step.id, 0),
                "drop_off_count": 0,  # computed below
            }
        )

    # Compute drop_off_count Python-side
    for i, item in enumerate(funnel_dicts):
        if i < len(funnel_dicts) - 1:
            next_count = funnel_dicts[i + 1]["response_count"]
            item["drop_off_count"] = max(0, item["response_count"] - next_count)
        else:
            item["drop_off_count"] = 0

    funnel = [StepFunnelItem(**d) for d in funnel_dicts]

    # Query 2: start word breakdown
    if session_ids:
        start_word_rows = (
            db.query(SurveyResponse.response_text, func.count(SurveyResponse.id))
            .filter(
                SurveyResponse.session_id.in_(session_ids),
                SurveyResponse.step_id == "__session_start__",
            )
            .group_by(SurveyResponse.response_text)
            .all()
        )
    else:
        start_word_rows = []

    start_words = [
        StartWordItem(word=row[0], count=row[1]) for row in start_word_rows
    ]

    return SurveyFunnelResponse(
        survey_id=survey_id,
        funnel=funnel,
        start_words=start_words,
    )


def get_export_data(
    db: Session,
    survey_id: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> list[ExportRow]:
    """Return session data rows for export.

    IMPORTANT: Only the first 12 characters of phone_hash are exposed.
    The full 64-character hash is NEVER returned.

    Args:
        db: Database session
        survey_id: Survey identifier
        start_date: Optional filter on started_at
        end_date: Optional filter on started_at

    Returns:
        List of ExportRow objects suitable for CSV/JSON/XLSX export
    """
    q = db.query(SurveySession).filter(SurveySession.survey_id == survey_id)

    if start_date is not None:
        q = q.filter(SurveySession.started_at >= start_date)
    if end_date is not None:
        q = q.filter(SurveySession.started_at <= end_date)

    sessions = q.all()

    rows: list[ExportRow] = []
    for s in sessions:
        rows.append(
            ExportRow(
                session_id=s.id,
                phone_hash_prefix=s.phone_hash[:12],  # NEVER expose full hash
                survey_id=s.survey_id,
                started_at=s.started_at,
                completed_at=s.completed_at,
                consent_given=s.consent_given,
                context=s.context or {},
            )
        )
    return rows


def generate_xlsx(rows: list[ExportRow]) -> bytes:
    """Generate an XLSX workbook from export rows.

    Args:
        rows: List of ExportRow objects

    Returns:
        Raw bytes of the XLSX file
    """
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Survey Export"

    headers = [
        "session_id",
        "phone_hash_prefix",
        "survey_id",
        "started_at",
        "completed_at",
        "consent_given",
        "context",
    ]
    ws.append(headers)

    for row in rows:
        ws.append(
            [
                row.session_id,
                row.phone_hash_prefix,
                row.survey_id,
                row.started_at.isoformat() if row.started_at else "",
                row.completed_at.isoformat() if row.completed_at else "",
                row.consent_given,
                str(row.context),
            ]
        )

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
