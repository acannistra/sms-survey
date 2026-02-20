"""Unit tests for survey engine service.

Tests the main survey orchestration logic including:
- Consent flow handling
- Input validation and retry logic
- Step progression
- Conditional branching
- Context management
- Terminal step handling
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timezone

from app.models.session import SurveySession
from app.models.response import SurveyResponse
from app.services.survey_engine import SurveyEngine, SurveyEngineError
from app.services.phone_hasher import PhoneHasher
from app.schemas.survey import QuestionType


@pytest.mark.unit
class TestSurveyEngine:
    """Test suite for SurveyEngine class."""

    def setup_method(self):
        """Set up test fixtures for each test."""
        # Will be overridden by individual tests
        pass

    # Test 1: Initialization
    def test_engine_initialization(self, db_session):
        """Test that survey engine initializes correctly."""
        engine = SurveyEngine(db_session)

        assert engine.db == db_session
        assert engine.loader is not None
        assert engine.renderer is not None

    # Test 2: Consent - Valid Acceptance
    def test_consent_accepted_yes(self, db_session, test_phone_hash):
        """Test consent acceptance with 'yes' response."""
        # Create session in consent state
        session = SurveySession(
            phone_hash=test_phone_hash,
            survey_id="volunteer_signup",
            survey_version="test",
            current_step="consent",
            consent_given=False,
            context={}
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)

        engine = SurveyEngine(db_session)

        # Process consent acceptance
        response_text, is_completed = engine.process_message(session, "yes")

        # Verify consent was granted
        assert session.consent_given is True
        assert session.consent_given_at is not None
        assert session.current_step == "ask_name"  # Moved to first question
        assert is_completed is False
        assert "first name" in response_text.lower()

        # Verify consent response was recorded
        responses = db_session.query(SurveyResponse).filter(
            SurveyResponse.session_id == session.id,
            SurveyResponse.step_id == "consent"
        ).all()
        assert len(responses) == 1
        assert responses[0].stored_value == "accepted"
        assert responses[0].is_valid is True

    # Test 3: Consent - Valid Decline
    def test_consent_declined_no(self, db_session, test_phone_hash):
        """Test consent decline with 'no' response."""
        session = SurveySession(
            phone_hash=test_phone_hash,
            survey_id="volunteer_signup",
            survey_version="test",
            current_step="consent",
            consent_given=False,
            context={}
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)

        engine = SurveyEngine(db_session)

        # Process consent decline
        response_text, is_completed = engine.process_message(session, "no")

        # Verify session completed without consent
        assert session.consent_given is False
        assert session.completed_at is not None
        assert is_completed is True
        assert "anytime to start over" in response_text.lower()

        # Verify decline response was recorded
        responses = db_session.query(SurveyResponse).filter(
            SurveyResponse.session_id == session.id,
            SurveyResponse.step_id == "consent"
        ).all()
        assert len(responses) == 1
        assert responses[0].stored_value == "declined"

    # Test 4: Consent - Invalid Response with Retry
    def test_consent_invalid_response_retry(self, db_session, test_phone_hash):
        """Test invalid consent response increments retry counter."""
        session = SurveySession(
            phone_hash=test_phone_hash,
            survey_id="volunteer_signup",
            survey_version="test",
            current_step="consent",
            consent_given=False,
            context={}
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)

        engine = SurveyEngine(db_session)

        # Process invalid consent
        response_text, is_completed = engine.process_message(session, "maybe")

        # Verify retry counter incremented
        assert session.retry_count == 1
        assert session.consent_given is False
        assert is_completed is False
        # Should return consent text again
        assert "YES to continue" in response_text

        # Verify invalid response was recorded
        responses = db_session.query(SurveyResponse).filter(
            SurveyResponse.session_id == session.id
        ).all()
        assert len(responses) == 1
        assert responses[0].is_valid is False

    # Test 5: Valid Text Input with Context Storage
    def test_valid_text_input_stores_context(self, db_session, test_phone_hash):
        """Test valid text input is stored in context."""
        session = SurveySession(
            phone_hash=test_phone_hash,
            survey_id="volunteer_signup",
            survey_version="test",
            current_step="ask_name",
            consent_given=True,
            context={}
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)

        engine = SurveyEngine(db_session)

        # Process valid name input
        response_text, is_completed = engine.process_message(session, "Alice")

        # Verify context was updated
        assert session.context["name"] == "Alice"
        assert session.current_step == "ask_zip"
        assert is_completed is False
        # Template should render with name
        assert "Alice" in response_text
        assert "ZIP" in response_text

        # Verify response was recorded
        responses = db_session.query(SurveyResponse).filter(
            SurveyResponse.session_id == session.id,
            SurveyResponse.step_id == "ask_name"
        ).all()
        assert len(responses) == 1
        assert responses[0].stored_value == "Alice"
        assert responses[0].is_valid is True

    # Test 6: Invalid Input Increments Retry
    def test_invalid_input_increments_retry(self, db_session, test_phone_hash):
        """Test invalid input increments retry counter and returns error."""
        session = SurveySession(
            phone_hash=test_phone_hash,
            survey_id="volunteer_signup",
            survey_version="test",
            current_step="ask_zip",
            consent_given=True,
            context={"name": "Alice"}
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)

        engine = SurveyEngine(db_session)

        # Process invalid ZIP code
        response_text, is_completed = engine.process_message(session, "1234")  # Only 4 digits

        # Verify retry counter incremented
        assert session.retry_count == 1
        assert session.current_step == "ask_zip"  # Stayed on same step
        assert is_completed is False
        assert "5-digit ZIP code" in response_text

        # Verify invalid response was recorded
        responses = db_session.query(SurveyResponse).filter(
            SurveyResponse.session_id == session.id,
            SurveyResponse.step_id == "ask_zip"
        ).all()
        assert len(responses) == 1
        assert responses[0].is_valid is False

    # Test 7: Max Retries Exceeded Skips Step
    def test_max_retries_exceeded_skips_step(self, db_session, test_phone_hash):
        """Test that max retries exceeded moves to next step."""
        session = SurveySession(
            phone_hash=test_phone_hash,
            survey_id="volunteer_signup",
            survey_version="test",
            current_step="ask_zip",
            consent_given=True,
            retry_count=2,  # Already at 2 retries
            context={"name": "Alice"}
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)

        engine = SurveyEngine(db_session)

        # Process third invalid attempt (should exceed max)
        response_text, is_completed = engine.process_message(session, "abcde")

        # Verify moved to next step
        assert session.retry_count == 0  # Reset by advance_step
        assert session.current_step == "ask_volunteer"  # Moved to next step
        assert is_completed is False
        assert "Too many invalid attempts" in response_text
        assert "volunteer for trail maintenance" in response_text

    # Test 8: Conditional Branching - True Path
    def test_conditional_branching_true_path(self, db_session, test_phone_hash):
        """Test conditional branching takes true path."""
        session = SurveySession(
            phone_hash=test_phone_hash,
            survey_id="volunteer_signup",
            survey_version="test",
            current_step="ask_volunteer",
            consent_given=True,
            context={"name": "Alice", "zip": "12345"}
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)

        engine = SurveyEngine(db_session)

        # Answer yes to volunteering
        response_text, is_completed = engine.process_message(session, "yes")

        # Verify branched to email collection (true path)
        assert session.context["wants_volunteer"] == "true"
        assert session.current_step == "ask_email"
        assert is_completed is False
        assert "email" in response_text.lower()

    # Test 9: Conditional Branching - False Path
    def test_conditional_branching_false_path(self, db_session, test_phone_hash):
        """Test conditional branching takes false path (default next)."""
        session = SurveySession(
            phone_hash=test_phone_hash,
            survey_id="volunteer_signup",
            survey_version="test",
            current_step="ask_volunteer",
            consent_given=True,
            context={"name": "Alice", "zip": "12345"}
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)

        engine = SurveyEngine(db_session)

        # Answer no to volunteering
        response_text, is_completed = engine.process_message(session, "no")

        # Verify branched to phone collection (default next)
        assert session.context["wants_volunteer"] == "false"
        assert session.current_step == "ask_phone"
        assert is_completed is False
        assert "phone number" in response_text.lower()

    # Test 10: Terminal Step Completes Survey
    def test_terminal_step_completes_survey(self, db_session, test_phone_hash):
        """Test that terminal step marks survey as completed."""
        session = SurveySession(
            phone_hash=test_phone_hash,
            survey_id="volunteer_signup",
            survey_version="test",
            current_step="ask_phone",
            consent_given=True,
            context={
                "name": "Alice",
                "zip": "12345",
                "wants_volunteer": "false"
            }
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)

        engine = SurveyEngine(db_session)

        # Provide phone number (last question before terminal)
        response_text, is_completed = engine.process_message(session, "5551234567")

        # Verify survey completed
        assert session.current_step == "completion"
        assert session.completed_at is not None
        assert is_completed is True
        assert "Thanks Alice" in response_text
        assert "Text STOP" in response_text

    # Test 11: Template Rendering with Context
    def test_template_rendering_with_context(self, db_session, test_phone_hash):
        """Test that Jinja2 templates render with context variables."""
        session = SurveySession(
            phone_hash=test_phone_hash,
            survey_id="volunteer_signup",
            survey_version="test",
            current_step="ask_name",
            consent_given=True,
            context={}
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)

        engine = SurveyEngine(db_session)

        # Process name
        response_text, _ = engine.process_message(session, "Bob")

        # Verify name was inserted into template
        assert "Bob" in response_text  # "Thanks Bob! What's your ZIP code?"

    # Test 12: Survey Not Found Error
    def test_survey_not_found_error(self, db_session, test_phone_hash):
        """Test that invalid survey ID raises error."""
        session = SurveySession(
            phone_hash=test_phone_hash,
            survey_id="nonexistent_survey",
            survey_version="test",
            current_step="consent",
            consent_given=False,
            context={}
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)

        engine = SurveyEngine(db_session)

        # Should raise SurveyEngineError
        with pytest.raises(SurveyEngineError, match="Processing failed"):
            engine.process_message(session, "yes")

    # Test 13: Invalid Step ID Error
    def test_invalid_step_id_error(self, db_session, test_phone_hash):
        """Test that invalid step ID raises error."""
        session = SurveySession(
            phone_hash=test_phone_hash,
            survey_id="volunteer_signup",
            survey_version="test",
            current_step="nonexistent_step",
            consent_given=True,
            context={}
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)

        engine = SurveyEngine(db_session)

        # Should raise SurveyEngineError
        with pytest.raises(SurveyEngineError, match="Invalid step"):
            engine.process_message(session, "test")

    # Test 14: Response Recording
    def test_response_recording(self, db_session, test_phone_hash):
        """Test that all responses are recorded in database."""
        session = SurveySession(
            phone_hash=test_phone_hash,
            survey_id="volunteer_signup",
            survey_version="test",
            current_step="ask_name",
            consent_given=True,
            context={}
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)

        engine = SurveyEngine(db_session)

        # Process valid input
        engine.process_message(session, "Charlie")

        # Verify response was recorded
        response = db_session.query(SurveyResponse).filter(
            SurveyResponse.session_id == session.id,
            SurveyResponse.step_id == "ask_name"
        ).first()

        assert response is not None
        assert response.response_text == "Charlie"
        assert response.stored_value == "Charlie"
        assert response.is_valid is True

    # Test 15: Multiple Retry Cycles
    def test_multiple_retry_cycles(self, db_session, test_phone_hash):
        """Test multiple invalid attempts followed by valid input."""
        session = SurveySession(
            phone_hash=test_phone_hash,
            survey_id="volunteer_signup",
            survey_version="test",
            current_step="ask_zip",
            consent_given=True,
            context={"name": "David"}
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)

        engine = SurveyEngine(db_session)

        # First invalid attempt
        engine.process_message(session, "123")
        assert session.retry_count == 1
        assert session.current_step == "ask_zip"

        # Second invalid attempt
        engine.process_message(session, "abcd")
        assert session.retry_count == 2
        assert session.current_step == "ask_zip"

        # Valid attempt - should reset retry count and advance
        engine.process_message(session, "12345")
        assert session.retry_count == 0
        assert session.current_step == "ask_volunteer"
