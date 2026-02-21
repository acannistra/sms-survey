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


@pytest.mark.unit
class TestShowIf:
    """Tests for show_if conditional step visibility feature."""

    # Test 16: show_if true — step is shown
    def test_show_if_true_step_shown(self, db_session, test_phone_hash):
        """Step with show_if evaluating true is presented normally."""
        # At msg_optional, start_word='common' — q6_pct_north should be shown
        session = SurveySession(
            phone_hash=test_phone_hash,
            survey_id="cba-snoq-25-26",
            survey_version="test",
            current_step="msg_optional",
            consent_given=True,
            context={"start_word": "common"}
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)

        engine = SurveyEngine(db_session)
        response_text, is_completed = engine.process_message(session, "Y")

        assert session.current_step == "q6_pct_north"
        assert is_completed is False
        assert "PCT North" in response_text

    # Test 17: show_if false — step is skipped transparently
    def test_show_if_false_step_skipped(self, db_session, test_phone_hash):
        """Step with show_if evaluating false is skipped; next visible step is shown."""
        # At msg_optional, start_word='survey' — q6_pct_north (show_if='common') should be skipped
        session = SurveySession(
            phone_hash=test_phone_hash,
            survey_id="cba-snoq-25-26",
            survey_version="test",
            current_step="msg_optional",
            consent_given=True,
            context={"start_word": "survey"}
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)

        engine = SurveyEngine(db_session)
        response_text, is_completed = engine.process_message(session, "Y")

        # q6 skipped; should land on q7_safety_issues
        assert session.current_step == "q7_safety_issues"
        assert is_completed is False
        assert "safety" in response_text.lower() or "crowding" in response_text.lower()

    # Test 18: No show_if — step always shown
    def test_no_show_if_always_shown(self, db_session, test_phone_hash):
        """Step without show_if is always presented regardless of context."""
        session = SurveySession(
            phone_hash=test_phone_hash,
            survey_id="cba-snoq-25-26",
            survey_version="test",
            current_step="q1_zip",
            consent_given=True,
            context={"start_word": "gold"}
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)

        engine = SurveyEngine(db_session)
        response_text, is_completed = engine.process_message(session, "98045")

        assert session.current_step == "q2_parking"
        assert is_completed is False

    # Test 19: show_if with undefined variable fails open (step is shown)
    def test_show_if_undefined_variable_fails_open(self, db_session):
        """show_if referencing an undefined context variable fails open — step is shown."""
        from app.schemas.survey import SurveyStep, QuestionType, ValidationRules, ChoiceOption
        from unittest.mock import MagicMock

        engine = SurveyEngine(db_session)

        step = SurveyStep(
            id="test_step",
            text="Test step",
            type=QuestionType.CHOICE,
            show_if="undefined_var == 'something'",  # variable not in context
            validation=ValidationRules(choices=[ChoiceOption(display="Y", value="yes")]),
            next="next_step"
        )
        next_step = SurveyStep(
            id="next_step",
            text="Next step",
            type=QuestionType.TERMINAL
        )

        mock_survey = MagicMock()
        engine.loader = MagicMock()
        engine.loader.get_step.side_effect = lambda s, sid: {
            "test_step": step, "next_step": next_step
        }.get(sid)

        # Should return the step itself (fail open), not skip to next_step
        result = engine._advance_to_visible_step(mock_survey, "test_step", {})
        assert result.id == "test_step"

    # Test 20: _advance_to_visible_step direct — cycle detection
    def test_advance_to_visible_step_cycle_detection(self, db_session):
        """_advance_to_visible_step raises SurveyEngineError on step cycle."""
        from app.schemas.survey import SurveyStep, QuestionType, ValidationRules, ChoiceOption
        from unittest.mock import MagicMock

        engine = SurveyEngine(db_session)

        # Build two steps that form a cycle via show_if
        step_a = SurveyStep(
            id="step_a",
            text="Step A",
            type=QuestionType.CHOICE,
            show_if="False",  # always skipped
            validation=ValidationRules(choices=[ChoiceOption(display="Y", value="yes")]),
            next="step_b"
        )
        step_b = SurveyStep(
            id="step_b",
            text="Step B",
            type=QuestionType.CHOICE,
            show_if="False",  # always skipped
            validation=ValidationRules(choices=[ChoiceOption(display="Y", value="yes")]),
            next="step_a"  # cycle back
        )

        mock_survey = MagicMock()
        engine.loader = MagicMock()
        engine.loader.get_step.side_effect = lambda survey, sid: {
            "step_a": step_a, "step_b": step_b
        }.get(sid)

        with pytest.raises(SurveyEngineError, match="Infinite loop"):
            engine._advance_to_visible_step(mock_survey, "step_a", {})

    # Test 21: _advance_to_visible_step — step not found raises SurveyEngineError
    def test_advance_to_visible_step_step_not_found(self, db_session):
        """_advance_to_visible_step raises SurveyEngineError when step ID doesn't exist."""
        from unittest.mock import MagicMock

        engine = SurveyEngine(db_session)
        mock_survey = MagicMock()
        engine.loader = MagicMock()
        engine.loader.get_step.return_value = None  # step not found

        with pytest.raises(SurveyEngineError, match="Step not found"):
            engine._advance_to_visible_step(mock_survey, "nonexistent_step", {})

    # Test 22: retry-exceeded when next step is terminal marks session completed
    def test_retry_exceeded_terminal_next_step(self, db_session, test_phone_hash):
        """When max retries exceeded and next step is terminal, session is marked completed."""
        session = SurveySession(
            phone_hash=test_phone_hash,
            survey_id="cba-snoq-25-26",
            survey_version="test",
            current_step="q12_pass_program",  # last question before end_full (terminal)
            consent_given=True,
            context={"start_word": "survey"},
            retry_count=2  # one more invalid reply will exceed max_retry_attempts=3
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)

        engine = SurveyEngine(db_session)

        # Third invalid reply triggers retry-exceeded path; next is end_full (terminal)
        response_text, is_completed = engine.process_message(session, "invalid")

        assert is_completed is True
        assert session.completed_at is not None
