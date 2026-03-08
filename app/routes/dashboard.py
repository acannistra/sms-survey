"""Dashboard API routes for survey monitoring and data export.

Provides endpoints for:
- Listing available surveys
- Per-survey statistics
- Step-level funnel analysis
- Data export in CSV, JSON, and XLSX formats

No authentication is added here — Cloudflare One handles auth at the edge.
"""

import csv
import io
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, Response
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.schemas.dashboard import (
    SurveyListResponse,
    SurveyStatsResponse,
    SurveyFunnelResponse,
)
from app.services.dashboard_service import (
    get_survey_list,
    get_survey_stats,
    get_survey_funnel,
    get_export_data,
    generate_xlsx,
)
from app.services.survey_loader import SurveyNotFoundError
from app.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


@router.get("/surveys", response_model=SurveyListResponse)
def list_surveys() -> SurveyListResponse:
    """List all available surveys with metadata."""
    return get_survey_list()


@router.get("/surveys/{survey_id}/stats", response_model=SurveyStatsResponse)
def survey_stats(
    survey_id: str,
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
) -> SurveyStatsResponse:
    """Return aggregate statistics for a survey.

    Args:
        survey_id: Survey identifier
        start_date: Optional ISO datetime — filter sessions started on or after
        end_date: Optional ISO datetime — filter sessions started on or before
        db: Database session (injected)

    Returns:
        SurveyStatsResponse with counts and completion percentage

    Raises:
        HTTPException 404: If survey_id not found
    """
    try:
        return get_survey_stats(db, survey_id, start_date, end_date)
    except SurveyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/surveys/{survey_id}/funnel", response_model=SurveyFunnelResponse)
def survey_funnel(
    survey_id: str,
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
) -> SurveyFunnelResponse:
    """Return step-level funnel analysis for a survey.

    Args:
        survey_id: Survey identifier
        start_date: Optional ISO datetime filter
        end_date: Optional ISO datetime filter
        db: Database session (injected)

    Returns:
        SurveyFunnelResponse with per-step counts and drop-off

    Raises:
        HTTPException 404: If survey_id not found
    """
    try:
        return get_survey_funnel(db, survey_id, start_date, end_date)
    except SurveyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/surveys/{survey_id}/export")
def survey_export(
    survey_id: str,
    format: str = Query("csv", pattern="^(csv|json|xlsx)$"),  # noqa: A002
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
) -> Response:
    """Export survey session data in CSV, JSON, or XLSX format.

    Args:
        survey_id: Survey identifier
        format: Export format — one of csv, json, xlsx (default: csv)
        start_date: Optional ISO datetime filter
        end_date: Optional ISO datetime filter
        db: Database session (injected)

    Returns:
        File download response with appropriate Content-Type and Content-Disposition

    Raises:
        HTTPException 404: If survey_id not found
    """
    try:
        rows = get_export_data(db, survey_id, start_date, end_date)
    except SurveyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    filename_base = f"survey_{survey_id}_export"

    if format == "csv":
        output = io.StringIO()
        fieldnames = [
            "session_id",
            "phone_hash_prefix",
            "survey_id",
            "started_at",
            "completed_at",
            "consent_given",
            "context",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "session_id": row.session_id,
                    "phone_hash_prefix": row.phone_hash_prefix,
                    "survey_id": row.survey_id,
                    "started_at": row.started_at.isoformat() if row.started_at else "",
                    "completed_at": row.completed_at.isoformat() if row.completed_at else "",
                    "consent_given": row.consent_given,
                    "context": json.dumps(row.context),
                }
            )
        content = output.getvalue()
        return StreamingResponse(
            io.BytesIO(content.encode("utf-8")),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{filename_base}.csv"'
            },
        )

    elif format == "json":
        data = [
            {
                "session_id": row.session_id,
                "phone_hash_prefix": row.phone_hash_prefix,
                "survey_id": row.survey_id,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                "consent_given": row.consent_given,
                "context": row.context,
            }
            for row in rows
        ]
        content_bytes = json.dumps(data, indent=2).encode("utf-8")
        return Response(
            content=content_bytes,
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{filename_base}.json"'
            },
        )

    else:  # xlsx
        xlsx_bytes = generate_xlsx(rows)
        return StreamingResponse(
            io.BytesIO(xlsx_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="{filename_base}.xlsx"'
            },
        )
