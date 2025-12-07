"""SurveySession model for tracking survey state and progress.

This module defines the SurveySession model which maintains the state
of a user's progress through a survey, including consent, current step, and context.
"""

from datetime import datetime, timezone
from typing import Optional, Any

from sqlalchemy import (
    Index,
    String,
    Integer,
    Boolean,
    DateTime,
    JSON,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.database import Base


class SurveySession(Base):
    """Model for tracking survey session state.

    A survey session represents a single user's progress through a survey.
    Users can initiate multiple survey sessions for the same survey (e.g.,
    responding from different trailheads), so no uniqueness constraint is
    enforced on phone_hash/survey_id combinations.

    Attributes:
        id: Primary key
        phone_hash: SHA-256 hash of phone number (64 hex chars)
        survey_id: Identifier of the survey being taken
        survey_version: Git commit SHA of survey definition
        current_step: ID of current step in survey
        consent_given: Whether user has given consent
        consent_requested_at: When consent was first requested
        consent_given_at: When user gave consent
        started_at: When survey session started
        updated_at: Last update timestamp
        completed_at: When survey was completed (NULL for active sessions)
        retry_count: Number of validation retries for current step
        context: JSONB field storing survey variables (e.g., name, zip)
    """

    __tablename__ = "survey_sessions"

    # Primary Key
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Phone Hash (never store plaintext phone numbers)
    phone_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="SHA-256 hash of phone number for privacy"
    )

    # Survey Identification
    survey_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Survey identifier from YAML filename"
    )
    survey_version: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Git commit SHA when survey was loaded"
    )

    # Current State
    current_step: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Current step ID in survey flow"
    )

    # Consent Tracking
    consent_given: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether user has consented to data collection"
    )
    consent_requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="When consent was first requested"
    )
    consent_given_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When user gave consent"
    )

    # Timestamps
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="When survey session started"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=lambda: datetime.now(timezone.utc),
        comment="Last update timestamp"
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When survey was completed (NULL for active sessions)"
    )

    # Retry Tracking
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of validation retries for current step"
    )

    # Context Storage (Jinja2 variables)
    context: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
        comment="JSON storage for survey variables (name, zip, etc.)"
    )

    # Relationship to SurveyResponse
    responses: Mapped[list["SurveyResponse"]] = relationship(
        "SurveyResponse",
        back_populates="session",
        cascade="all, delete-orphan",
    )

    # Indexes
    __table_args__ = (
        # Index for phone_hash + survey_id lookups
        Index("idx_phone_hash_survey", "phone_hash", "survey_id"),
        # Index for finding stale sessions
        Index("idx_updated_at", "updated_at"),
        # Index for finding active sessions
        Index("idx_completed_at", "completed_at"),
    )

    def increment_retry(self) -> None:
        """Increment retry count for current step.

        Used when user provides invalid input. Should be followed by
        a commit to persist the change.
        """
        self.retry_count += 1

    def reset_retry(self) -> None:
        """Reset retry count to zero.

        Called when advancing to a new step or after user provides
        valid input.
        """
        self.retry_count = 0

    def advance_step(self, next_step_id: str) -> None:
        """Advance to the next step in the survey.

        Args:
            next_step_id: ID of the next step to advance to

        Note:
            Automatically resets retry_count to 0.
        """
        self.current_step = next_step_id
        self.reset_retry()

    def mark_completed(self) -> None:
        """Mark the survey session as completed.

        Sets completed_at to current UTC time.
        """
        self.completed_at = datetime.now(timezone.utc)

    def update_context(self, key: str, value: Any) -> None:
        """Update a single context variable.

        Args:
            key: Variable name (e.g., "name", "zip")
            value: Value to store

        Note:
            For JSONB fields, you must explicitly flag the object as modified
            or reassign it to trigger SQLAlchemy's change tracking.
        """
        # Create new dict to trigger SQLAlchemy change detection
        new_context = dict(self.context)
        new_context[key] = value
        self.context = new_context

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"<SurveySession(id={self.id}, "
            f"phone_hash={self.phone_hash[:12]}..., "
            f"survey_id={self.survey_id}, "
            f"current_step={self.current_step}, "
            f"completed={self.completed_at is not None})>"
        )
