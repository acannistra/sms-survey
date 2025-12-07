"""Unit tests for SurveySession model helper methods.

These tests verify the behavior of SurveySession model methods without
requiring a database connection. They test business logic in isolation.
"""

from datetime import datetime, timezone

import pytest

from app.models.session import SurveySession


class TestSurveySessionHelperMethods:
    """Test SurveySession helper methods."""

    def test_increment_retry(self):
        """Test incrementing retry count."""
        session = SurveySession(
            phone_hash="a" * 64,
            survey_id="test_survey",
            survey_version="abc123",
            current_step="step1",
            retry_count=0,
        )

        # Initial retry count should be 0
        assert session.retry_count == 0

        # Increment once
        session.increment_retry()
        assert session.retry_count == 1

        # Increment again
        session.increment_retry()
        assert session.retry_count == 2

    def test_reset_retry(self):
        """Test resetting retry count to zero."""
        session = SurveySession(
            phone_hash="a" * 64,
            survey_id="test_survey",
            survey_version="abc123",
            current_step="step1",
            retry_count=5,
        )

        # Initial retry count should be 5
        assert session.retry_count == 5

        # Reset to zero
        session.reset_retry()
        assert session.retry_count == 0

    def test_advance_step(self):
        """Test advancing to next step resets retry count."""
        session = SurveySession(
            phone_hash="a" * 64,
            survey_id="test_survey",
            survey_version="abc123",
            current_step="step1",
            retry_count=3,
        )

        # Advance to next step
        session.advance_step("step2")

        # Should update step and reset retry count
        assert session.current_step == "step2"
        assert session.retry_count == 0

    def test_mark_completed(self):
        """Test marking session as completed."""
        session = SurveySession(
            phone_hash="a" * 64,
            survey_id="test_survey",
            survey_version="abc123",
            current_step="step1",
            completed_at=None,
        )

        # Initially not completed
        assert session.completed_at is None

        # Mark as completed
        before = datetime.now(timezone.utc)
        session.mark_completed()
        after = datetime.now(timezone.utc)

        # Should set completed_at to current time
        assert session.completed_at is not None
        assert before <= session.completed_at <= after

    def test_update_context(self):
        """Test updating context variables."""
        session = SurveySession(
            phone_hash="a" * 64,
            survey_id="test_survey",
            survey_version="abc123",
            current_step="step1",
            context={},
        )

        # Initially empty
        assert session.context == {}

        # Add a variable
        session.update_context("name", "John Doe")
        assert session.context == {"name": "John Doe"}

        # Add another variable
        session.update_context("zip", "12345")
        assert session.context == {"name": "John Doe", "zip": "12345"}

        # Update existing variable
        session.update_context("name", "Jane Doe")
        assert session.context == {"name": "Jane Doe", "zip": "12345"}

    def test_update_context_preserves_existing_keys(self):
        """Test that updating one context key preserves others."""
        session = SurveySession(
            phone_hash="a" * 64,
            survey_id="test_survey",
            survey_version="abc123",
            current_step="step1",
            context={"existing": "value"},
        )

        # Add new key
        session.update_context("name", "John")

        # Should preserve existing key
        assert session.context == {"existing": "value", "name": "John"}

    def test_repr(self):
        """Test string representation."""
        session = SurveySession(
            id=123,
            phone_hash="abcdef1234567890" * 4,  # 64 chars
            survey_id="test_survey",
            survey_version="abc123",
            current_step="step1",
            completed_at=None,
        )

        repr_str = repr(session)

        # Should include key information
        assert "SurveySession" in repr_str
        assert "id=123" in repr_str
        assert "survey_id=test_survey" in repr_str
        assert "current_step=step1" in repr_str
        assert "completed=False" in repr_str

        # Should truncate phone_hash for privacy
        assert "abcdef123456..." in repr_str
        assert "abcdef1234567890" * 4 not in repr_str  # Full hash not shown

    def test_repr_completed_session(self):
        """Test string representation of completed session."""
        session = SurveySession(
            id=456,
            phone_hash="a" * 64,
            survey_id="test_survey",
            survey_version="abc123",
            current_step="terminal",
            completed_at=datetime.now(timezone.utc),
        )

        repr_str = repr(session)

        # Should indicate completion
        assert "completed=True" in repr_str
