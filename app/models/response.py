"""SurveyResponse model for storing individual survey responses.

This module defines the SurveyResponse model which stores each answer
provided by a user during their survey session.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Index,
    String,
    Text,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.database import Base


class SurveyResponse(Base):
    """Model for storing individual survey responses.

    Each response represents a single answer to a survey step. Responses
    are linked to a survey session and are automatically deleted when the
    parent session is deleted (CASCADE).

    Attributes:
        id: Primary key
        session_id: Foreign key to survey_sessions table
        step_id: ID of the survey step being answered
        response_text: Raw text response from user
        stored_value: Processed/validated value stored in context
        responded_at: When the response was submitted
        is_valid: Whether the response passed validation
        session: Relationship to parent SurveySession
    """

    __tablename__ = "survey_responses"

    # Primary Key
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Foreign Key to SurveySession
    session_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("survey_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Foreign key to survey_sessions table"
    )

    # Response Data
    step_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="ID of the survey step being answered"
    )
    response_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Raw text response from user"
    )
    stored_value: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Processed/validated value stored in context"
    )

    # Metadata
    responded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="When the response was submitted"
    )
    is_valid: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether the response passed validation"
    )

    # Relationship to SurveySession
    session: Mapped["SurveySession"] = relationship(
        "SurveySession",
        back_populates="responses",
    )

    # Indexes
    __table_args__ = (
        # Index for querying responses by session and step
        Index("idx_session_step", "session_id", "step_id"),
    )

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"<SurveyResponse(id={self.id}, "
            f"session_id={self.session_id}, "
            f"step_id={self.step_id}, "
            f"is_valid={self.is_valid})>"
        )
