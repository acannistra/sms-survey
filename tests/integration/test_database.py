"""Integration tests for database operations.

These tests verify the complete database layer including:
- Session creation and querying
- Response creation and cascade delete
- OptOut operations
- Pessimistic locking (SELECT FOR UPDATE)
- Relationships between models
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models.session import SurveySession
from app.models.response import SurveyResponse
from app.models.optout import OptOut


class TestSurveySessionIntegration:
    """Integration tests for SurveySession model."""

    def test_create_and_query_session(
        self, db_session, sample_phone_hash, sample_survey_id, sample_survey_version
    ):
        """Test creating and querying a survey session."""
        # Create session
        session = SurveySession(
            phone_hash=sample_phone_hash,
            survey_id=sample_survey_id,
            survey_version=sample_survey_version,
            current_step="consent",
            consent_given=False,
            retry_count=0,
            context={},
        )
        db_session.add(session)
        db_session.commit()

        # Query it back
        result = db_session.query(SurveySession).filter(
            SurveySession.phone_hash == sample_phone_hash
        ).first()

        assert result is not None
        assert result.phone_hash == sample_phone_hash
        assert result.survey_id == sample_survey_id
        assert result.current_step == "consent"
        assert result.consent_given is False
        assert result.completed_at is None

    def test_multiple_sessions_allowed(
        self, db_session, sample_phone_hash, sample_survey_id, sample_survey_version
    ):
        """Test that multiple sessions can be created for same phone/survey."""
        # Create first session
        session1 = SurveySession(
            phone_hash=sample_phone_hash,
            survey_id=sample_survey_id,
            survey_version=sample_survey_version,
            current_step="step1",
            consent_given=True,
            retry_count=0,
            context={},
        )
        db_session.add(session1)
        db_session.commit()

        # Create second session for same phone/survey
        session2 = SurveySession(
            phone_hash=sample_phone_hash,
            survey_id=sample_survey_id,
            survey_version=sample_survey_version,
            current_step="step1",
            consent_given=True,
            retry_count=0,
            context={},
        )
        db_session.add(session2)
        db_session.commit()

        # Both should exist
        sessions = db_session.query(SurveySession).filter(
            SurveySession.phone_hash == sample_phone_hash
        ).all()
        assert len(sessions) == 2

    def test_pessimistic_locking(
        self, db_session, sample_phone_hash, sample_survey_id, sample_survey_version
    ):
        """Test SELECT FOR UPDATE (pessimistic locking)."""
        # Create session
        session = SurveySession(
            phone_hash=sample_phone_hash,
            survey_id=sample_survey_id,
            survey_version=sample_survey_version,
            current_step="step1",
            consent_given=True,
            retry_count=0,
            context={},
        )
        db_session.add(session)
        db_session.commit()

        # Query with FOR UPDATE lock
        locked_session = db_session.query(SurveySession).filter(
            SurveySession.phone_hash == sample_phone_hash,
            SurveySession.id == session.id,
        ).with_for_update().first()

        assert locked_session is not None
        assert locked_session.id == session.id

        # Modify and commit
        locked_session.current_step = "step2"
        db_session.commit()

        # Verify change
        updated = db_session.query(SurveySession).get(session.id)
        assert updated.current_step == "step2"

    def test_context_jsonb_storage(
        self, db_session, sample_phone_hash, sample_survey_id, sample_survey_version
    ):
        """Test storing and retrieving JSONB context data."""
        # Create session with context
        session = SurveySession(
            phone_hash=sample_phone_hash,
            survey_id=sample_survey_id,
            survey_version=sample_survey_version,
            current_step="step1",
            consent_given=True,
            retry_count=0,
            context={"name": "John Doe", "zip": "12345", "age": 30},
        )
        db_session.add(session)
        db_session.commit()

        # Query it back
        result = db_session.query(SurveySession).get(session.id)
        assert result.context == {"name": "John Doe", "zip": "12345", "age": 30}

        # Update context
        result.update_context("email", "john@example.com")
        db_session.commit()

        # Verify update
        updated = db_session.query(SurveySession).get(session.id)
        assert updated.context["email"] == "john@example.com"
        assert updated.context["name"] == "John Doe"  # Preserved


class TestSurveyResponseIntegration:
    """Integration tests for SurveyResponse model."""

    def test_create_response_with_session(
        self, db_session, sample_phone_hash, sample_survey_id, sample_survey_version
    ):
        """Test creating a response linked to a session."""
        # Create session
        session = SurveySession(
            phone_hash=sample_phone_hash,
            survey_id=sample_survey_id,
            survey_version=sample_survey_version,
            current_step="step1",
            consent_given=True,
            retry_count=0,
            context={},
        )
        db_session.add(session)
        db_session.commit()

        # Create response
        response = SurveyResponse(
            session_id=session.id,
            step_id="step1",
            response_text="John Doe",
            stored_value="John Doe",
            is_valid=True,
        )
        db_session.add(response)
        db_session.commit()

        # Query response
        result = db_session.query(SurveyResponse).filter(
            SurveyResponse.session_id == session.id
        ).first()

        assert result is not None
        assert result.step_id == "step1"
        assert result.response_text == "John Doe"
        assert result.is_valid is True

    def test_cascade_delete(
        self, db_session, sample_phone_hash, sample_survey_id, sample_survey_version
    ):
        """Test that responses are deleted when session is deleted."""
        # Create session
        session = SurveySession(
            phone_hash=sample_phone_hash,
            survey_id=sample_survey_id,
            survey_version=sample_survey_version,
            current_step="step1",
            consent_given=True,
            retry_count=0,
            context={},
        )
        db_session.add(session)
        db_session.commit()

        # Create multiple responses
        response1 = SurveyResponse(
            session_id=session.id,
            step_id="step1",
            response_text="Answer 1",
            stored_value="Answer 1",
            is_valid=True,
        )
        response2 = SurveyResponse(
            session_id=session.id,
            step_id="step2",
            response_text="Answer 2",
            stored_value="Answer 2",
            is_valid=True,
        )
        db_session.add_all([response1, response2])
        db_session.commit()

        # Verify responses exist
        responses = db_session.query(SurveyResponse).filter(
            SurveyResponse.session_id == session.id
        ).all()
        assert len(responses) == 2

        # Delete session
        db_session.delete(session)
        db_session.commit()

        # Verify responses are gone (CASCADE)
        responses_after = db_session.query(SurveyResponse).filter(
            SurveyResponse.session_id == session.id
        ).all()
        assert len(responses_after) == 0

    def test_response_relationship(
        self, db_session, sample_phone_hash, sample_survey_id, sample_survey_version
    ):
        """Test relationship between session and responses."""
        # Create session
        session = SurveySession(
            phone_hash=sample_phone_hash,
            survey_id=sample_survey_id,
            survey_version=sample_survey_version,
            current_step="step1",
            consent_given=True,
            retry_count=0,
            context={},
        )
        db_session.add(session)
        db_session.commit()

        # Create responses
        response1 = SurveyResponse(
            session_id=session.id,
            step_id="step1",
            response_text="Answer 1",
            is_valid=True,
        )
        response2 = SurveyResponse(
            session_id=session.id,
            step_id="step2",
            response_text="Answer 2",
            is_valid=True,
        )
        db_session.add_all([response1, response2])
        db_session.commit()

        # Access responses through relationship
        session_with_responses = db_session.query(SurveySession).get(session.id)
        assert len(session_with_responses.responses) == 2
        assert session_with_responses.responses[0].step_id == "step1"
        assert session_with_responses.responses[1].step_id == "step2"


class TestOptOutIntegration:
    """Integration tests for OptOut model."""

    def test_optout_workflow(self, db_session, sample_phone_hash):
        """Test complete opt-out workflow."""
        # Initially not opted out
        assert OptOut.is_opted_out(db_session, sample_phone_hash) is False

        # Opt out
        optout = OptOut.add_optout(db_session, sample_phone_hash, "STOP")
        db_session.commit()

        # Should be opted out
        assert OptOut.is_opted_out(db_session, sample_phone_hash) is True

        # Opt back in
        removed = OptOut.remove_optout(db_session, sample_phone_hash)
        db_session.commit()

        assert removed is True
        assert OptOut.is_opted_out(db_session, sample_phone_hash) is False

    def test_optout_unique_constraint(self, db_session, sample_phone_hash):
        """Test that phone_hash is unique in optouts table."""
        # Add first opt-out
        OptOut.add_optout(db_session, sample_phone_hash, "STOP")
        db_session.commit()

        # Try to add again - should update, not create duplicate
        OptOut.add_optout(db_session, sample_phone_hash, "UNSUBSCRIBE")
        db_session.commit()

        # Should only have one record
        optouts = db_session.query(OptOut).filter(
            OptOut.phone_hash == sample_phone_hash
        ).all()
        assert len(optouts) == 1
        assert optouts[0].opt_out_message == "UNSUBSCRIBE"

    def test_optout_different_phones(self, db_session):
        """Test opt-out with multiple different phone hashes."""
        phone1 = "a" * 64
        phone2 = "b" * 64
        phone3 = "c" * 64

        # Opt out all three
        OptOut.add_optout(db_session, phone1, "STOP")
        OptOut.add_optout(db_session, phone2, "STOP")
        OptOut.add_optout(db_session, phone3, "STOP")
        db_session.commit()

        # All should be opted out
        assert OptOut.is_opted_out(db_session, phone1) is True
        assert OptOut.is_opted_out(db_session, phone2) is True
        assert OptOut.is_opted_out(db_session, phone3) is True

        # Opt back in one
        OptOut.remove_optout(db_session, phone2)
        db_session.commit()

        # Should only affect that one
        assert OptOut.is_opted_out(db_session, phone1) is True
        assert OptOut.is_opted_out(db_session, phone2) is False
        assert OptOut.is_opted_out(db_session, phone3) is True


class TestIndexes:
    """Test that indexes are working correctly."""

    def test_phone_hash_index(
        self, db_session, sample_survey_id, sample_survey_version
    ):
        """Test querying by phone_hash uses index."""
        phone_hash = "test_hash_" + "a" * 54

        # Create session
        session = SurveySession(
            phone_hash=phone_hash,
            survey_id=sample_survey_id,
            survey_version=sample_survey_version,
            current_step="step1",
            consent_given=True,
            retry_count=0,
            context={},
        )
        db_session.add(session)
        db_session.commit()

        # Query by phone_hash
        result = db_session.query(SurveySession).filter(
            SurveySession.phone_hash == phone_hash
        ).first()

        assert result is not None
        assert result.phone_hash == phone_hash

    def test_session_id_index(
        self, db_session, sample_phone_hash, sample_survey_id, sample_survey_version
    ):
        """Test querying responses by session_id uses index."""
        # Create session
        session = SurveySession(
            phone_hash=sample_phone_hash,
            survey_id=sample_survey_id,
            survey_version=sample_survey_version,
            current_step="step1",
            consent_given=True,
            retry_count=0,
            context={},
        )
        db_session.add(session)
        db_session.commit()

        # Create response
        response = SurveyResponse(
            session_id=session.id,
            step_id="step1",
            response_text="Test",
            is_valid=True,
        )
        db_session.add(response)
        db_session.commit()

        # Query by session_id
        results = db_session.query(SurveyResponse).filter(
            SurveyResponse.session_id == session.id
        ).all()

        assert len(results) == 1
        assert results[0].session_id == session.id
