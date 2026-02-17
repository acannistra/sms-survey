"""Integration tests for Twilio webhook flow.

Tests complete SMS conversation flows including:
- Start word detection and session creation
- Consent flow
- Question progression
- Validation and retries
- Conditional branching
- Survey completion
- Opt-out handling
"""

import pytest
from fastapi.testclient import TestClient

from app.models.session import SurveySession
from app.models.response import SurveyResponse
from app.models.optout import OptOut
from app.services.phone_hasher import PhoneHasher


@pytest.mark.integration
class TestWebhookFlow:
    """Test suite for webhook SMS flows."""

    def create_twilio_request(
        self,
        from_number: str,
        body: str,
        to_number: str = "+15551234567"
    ) -> dict:
        """Helper to create Twilio webhook request data.

        Args:
            from_number: Sender phone number
            body: SMS message body
            to_number: Recipient phone number

        Returns:
            dict: Twilio webhook form data
        """
        return {
            "MessageSid": "SM1234567890abcdef1234567890abcdef",
            "AccountSid": "AC1234567890abcdef1234567890abcdef",
            "From": from_number,
            "To": to_number,
            "Body": body,
            "NumMedia": "0"
        }

    # Test 1: New User Sends Start Word
    def test_start_word_creates_session_sends_consent(
        self,
        test_client,
        db_session,
        test_phone_number
    ):
        """Test that start word creates new session and sends consent message."""
        request_data = self.create_twilio_request(test_phone_number, "volunteer")

        response = test_client.post("/api/webhook/sms", data=request_data)

        # Verify response
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/xml; charset=utf-8"
        assert b"<Response>" in response.content
        assert b"YES to continue" in response.content

        # Verify session was created
        phone_hash = PhoneHasher.hash_phone(test_phone_number)
        session = db_session.query(SurveySession).filter(
            SurveySession.phone_hash == phone_hash,
            SurveySession.survey_id == "volunteer_signup"
        ).first()

        assert session is not None
        assert session.current_step == "consent"
        assert session.consent_given is False
        assert session.completed_at is None

    # Test 2: User Accepts Consent
    def test_consent_acceptance(self, test_client, db_session, test_phone_number):
        """Test consent acceptance flow."""
        # Create existing session in consent state
        phone_hash = PhoneHasher.hash_phone(test_phone_number)
        session = SurveySession(
            phone_hash=phone_hash,
            survey_id="volunteer_signup",
            survey_version="test",
            current_step="consent",
            consent_given=False,
            context={}
        )
        db_session.add(session)
        db_session.commit()

        # Send consent acceptance
        request_data = self.create_twilio_request(test_phone_number, "yes")
        response = test_client.post("/api/webhook/sms", data=request_data)

        # Verify response
        assert response.status_code == 200
        assert b"first name" in response.content.lower()

        # Verify session updated
        db_session.refresh(session)
        assert session.consent_given is True
        assert session.consent_given_at is not None
        assert session.current_step == "ask_name"

    # Test 3: User Declines Consent
    def test_consent_decline(self, test_client, db_session, test_phone_number):
        """Test consent decline flow."""
        # Create existing session in consent state
        phone_hash = PhoneHasher.hash_phone(test_phone_number)
        session = SurveySession(
            phone_hash=phone_hash,
            survey_id="volunteer_signup",
            survey_version="test",
            current_step="consent",
            consent_given=False,
            context={}
        )
        db_session.add(session)
        db_session.commit()

        # Send consent decline
        request_data = self.create_twilio_request(test_phone_number, "no")
        response = test_client.post("/api/webhook/sms", data=request_data)

        # Verify response
        assert response.status_code == 200
        assert b"start over" in response.content.lower()

        # Verify session completed
        db_session.refresh(session)
        assert session.consent_given is False
        assert session.completed_at is not None

    # Test 4: Valid Answer Progresses to Next Question
    def test_valid_answer_progression(self, test_client, db_session, test_phone_number):
        """Test valid answer moves to next question."""
        # Create session at name question
        phone_hash = PhoneHasher.hash_phone(test_phone_number)
        session = SurveySession(
            phone_hash=phone_hash,
            survey_id="volunteer_signup",
            survey_version="test",
            current_step="ask_name",
            consent_given=True,
            context={}
        )
        db_session.add(session)
        db_session.commit()

        # Send valid name
        request_data = self.create_twilio_request(test_phone_number, "Alice")
        response = test_client.post("/api/webhook/sms", data=request_data)

        # Verify response
        assert response.status_code == 200
        assert b"Alice" in response.content  # Template rendered
        assert b"ZIP" in response.content

        # Verify session updated
        db_session.refresh(session)
        assert session.context["name"] == "Alice"
        assert session.current_step == "ask_zip"

        # Verify response recorded
        response_record = db_session.query(SurveyResponse).filter(
            SurveyResponse.session_id == session.id,
            SurveyResponse.step_id == "ask_name"
        ).first()
        assert response_record is not None
        assert response_record.stored_value == "Alice"
        assert response_record.is_valid is True

    # Test 5: Invalid Answer Returns Error Message
    def test_invalid_answer_error(self, test_client, db_session, test_phone_number):
        """Test invalid answer returns error and increments retry."""
        # Create session at ZIP question
        phone_hash = PhoneHasher.hash_phone(test_phone_number)
        session = SurveySession(
            phone_hash=phone_hash,
            survey_id="volunteer_signup",
            survey_version="test",
            current_step="ask_zip",
            consent_given=True,
            context={"name": "Alice"}
        )
        db_session.add(session)
        db_session.commit()

        # Send invalid ZIP (4 digits instead of 5)
        request_data = self.create_twilio_request(test_phone_number, "1234")
        response = test_client.post("/api/webhook/sms", data=request_data)

        # Verify error response
        assert response.status_code == 200
        assert b"5-digit ZIP code" in response.content

        # Verify retry counter incremented
        db_session.refresh(session)
        assert session.retry_count == 1
        assert session.current_step == "ask_zip"  # Stayed on same step

    # Test 6: Max Retries Exceeded Skips Question
    def test_max_retries_skips_question(self, test_client, db_session, test_phone_number):
        """Test that exceeding max retries skips question."""
        # Create session with 2 retries already
        phone_hash = PhoneHasher.hash_phone(test_phone_number)
        session = SurveySession(
            phone_hash=phone_hash,
            survey_id="volunteer_signup",
            survey_version="test",
            current_step="ask_zip",
            consent_given=True,
            retry_count=2,
            context={"name": "Alice"}
        )
        db_session.add(session)
        db_session.commit()

        # Send third invalid attempt
        request_data = self.create_twilio_request(test_phone_number, "abcde")
        response = test_client.post("/api/webhook/sms", data=request_data)

        # Verify moved to next question
        assert response.status_code == 200
        assert b"Too many invalid attempts" in response.content
        assert b"volunteer for trail maintenance" in response.content

        # Verify session moved forward
        db_session.refresh(session)
        assert session.current_step == "ask_volunteer"
        assert session.retry_count == 0  # Reset

    # Test 7: Complete Survey Flow
    def test_complete_survey_flow(self, test_client, db_session, test_phone_number):
        """Test complete survey from start to finish."""
        phone_hash = PhoneHasher.hash_phone(test_phone_number)

        # 1. Start with start word
        response = test_client.post(
            "/api/webhook/sms",
            data=self.create_twilio_request(test_phone_number, "volunteer")
        )
        assert b"YES to continue" in response.content

        # 2. Accept consent
        response = test_client.post(
            "/api/webhook/sms",
            data=self.create_twilio_request(test_phone_number, "yes")
        )
        assert b"first name" in response.content.lower()

        # 3. Provide name
        response = test_client.post(
            "/api/webhook/sms",
            data=self.create_twilio_request(test_phone_number, "Bob")
        )
        assert b"Bob" in response.content
        assert b"ZIP" in response.content

        # 4. Provide ZIP
        response = test_client.post(
            "/api/webhook/sms",
            data=self.create_twilio_request(test_phone_number, "12345")
        )
        assert b"volunteer for trail maintenance" in response.content

        # 5. Decline volunteering
        response = test_client.post(
            "/api/webhook/sms",
            data=self.create_twilio_request(test_phone_number, "no")
        )
        assert b"phone number" in response.content.lower()

        # 6. Provide phone
        response = test_client.post(
            "/api/webhook/sms",
            data=self.create_twilio_request(test_phone_number, "5551234567")
        )
        assert b"Thanks Bob" in response.content
        assert b"Text STOP" in response.content

        # Verify session completed
        session = db_session.query(SurveySession).filter(
            SurveySession.phone_hash == phone_hash
        ).first()
        assert session.completed_at is not None
        assert session.current_step == "completion"

    # Test 8: Conditional Branching - Volunteer Path
    def test_conditional_branch_volunteer_path(
        self,
        test_client,
        db_session,
        test_phone_number
    ):
        """Test conditional branching takes volunteer path."""
        # Create session at volunteer question
        phone_hash = PhoneHasher.hash_phone(test_phone_number)
        session = SurveySession(
            phone_hash=phone_hash,
            survey_id="volunteer_signup",
            survey_version="test",
            current_step="ask_volunteer",
            consent_given=True,
            context={"name": "Carol", "zip": "12345"}
        )
        db_session.add(session)
        db_session.commit()

        # Say yes to volunteering
        request_data = self.create_twilio_request(test_phone_number, "yes")
        response = test_client.post("/api/webhook/sms", data=request_data)

        # Verify branched to email collection
        assert response.status_code == 200
        assert b"email" in response.content.lower()

        db_session.refresh(session)
        assert session.current_step == "ask_email"
        assert session.context["wants_volunteer"] == "true"

    # Test 9: Opt-Out with STOP Keyword
    def test_optout_stop_keyword(self, test_client, db_session, test_phone_number):
        """Test that STOP keyword opts user out."""
        phone_hash = PhoneHasher.hash_phone(test_phone_number)

        # Send STOP keyword
        request_data = self.create_twilio_request(test_phone_number, "STOP")
        response = test_client.post("/api/webhook/sms", data=request_data)

        # Verify opt-out response
        assert response.status_code == 200
        assert b"unsubscribed" in response.content.lower()
        assert b"Text START" in response.content

        # Verify opt-out record created
        optout = db_session.query(OptOut).filter(
            OptOut.phone_hash == phone_hash
        ).first()
        assert optout is not None
        assert optout.opted_out_at is not None

    # Test 10: Opted-Out User Gets No Response
    def test_opted_out_user_no_response(self, test_client, db_session, test_phone_number):
        """Test that opted-out user receives empty response."""
        phone_hash = PhoneHasher.hash_phone(test_phone_number)

        # Create opt-out record
        OptOut.add_optout(db_session, phone_hash, "STOP")
        db_session.commit()

        # Send any message
        request_data = self.create_twilio_request(test_phone_number, "volunteer")
        response = test_client.post("/api/webhook/sms", data=request_data)

        # Verify empty response
        assert response.status_code == 200
        assert b"<Response />" in response.content or b"<Response/>" in response.content

    # Test 11: Opt-In with START Keyword
    def test_optin_start_keyword(self, test_client, db_session, test_phone_number):
        """Test that START keyword opts user back in."""
        phone_hash = PhoneHasher.hash_phone(test_phone_number)

        # Create opt-out record
        OptOut.add_optout(db_session, phone_hash, "STOP")
        db_session.commit()

        # Send START to opt back in
        request_data = self.create_twilio_request(test_phone_number, "START")
        response = test_client.post("/api/webhook/sms", data=request_data)

        # Verify welcome back message
        assert response.status_code == 200
        assert b"Welcome back" in response.content or b"opted back in" in response.content

        # Verify opt-out record removed
        optout = db_session.query(OptOut).filter(
            OptOut.phone_hash == phone_hash
        ).first()
        assert optout is None

    # Test 12: No Active Session Ignores Message
    def test_no_active_session_ignores_message(
        self,
        test_client,
        db_session,
        test_phone_number
    ):
        """Test that messages without active session are ignored."""
        # Send random message without starting survey
        request_data = self.create_twilio_request(test_phone_number, "hello")
        response = test_client.post("/api/webhook/sms", data=request_data)

        # Verify empty response
        assert response.status_code == 200
        assert b"<Response" in response.content

    # Test 13: Start Word Abandons Existing Session
    def test_start_word_abandons_existing_session(
        self,
        test_client,
        db_session,
        test_phone_number
    ):
        """Test that start word creates new session and abandons old one."""
        phone_hash = PhoneHasher.hash_phone(test_phone_number)

        # Create existing active session
        old_session = SurveySession(
            phone_hash=phone_hash,
            survey_id="volunteer_signup",
            survey_version="test",
            current_step="ask_zip",
            consent_given=True,
            context={"name": "Alice"}
        )
        db_session.add(old_session)
        db_session.commit()
        old_session_id = old_session.id

        # Send start word
        request_data = self.create_twilio_request(test_phone_number, "volunteer")
        response = test_client.post("/api/webhook/sms", data=request_data)

        # Verify consent message returned
        assert b"YES to continue" in response.content

        # Verify old session marked as completed
        db_session.refresh(old_session)
        assert old_session.completed_at is not None

        # Verify new session created
        new_sessions = db_session.query(SurveySession).filter(
            SurveySession.phone_hash == phone_hash,
            SurveySession.completed_at.is_(None)
        ).all()
        assert len(new_sessions) == 1
        assert new_sessions[0].id != old_session_id
        assert new_sessions[0].current_step == "consent"

    # Test 14: Survey Not Found Returns Error
    def test_survey_not_found_error(self, test_client, db_session, test_phone_number):
        """Test that invalid survey ID returns error message."""
        phone_hash = PhoneHasher.hash_phone(test_phone_number)

        # Create session with invalid survey ID
        session = SurveySession(
            phone_hash=phone_hash,
            survey_id="nonexistent_survey",
            survey_version="test",
            current_step="consent",
            consent_given=False,
            context={}
        )
        db_session.add(session)
        db_session.commit()

        # Send message
        request_data = self.create_twilio_request(test_phone_number, "yes")
        response = test_client.post("/api/webhook/sms", data=request_data)

        # Verify error response
        assert response.status_code == 200
        assert b"error" in response.content.lower()

    # Test 15: Multiple Opt-Out Keywords
    @pytest.mark.parametrize("keyword", ["STOP", "stopall", "UNSUBSCRIBE", "cancel", "END", "quit"])
    def test_multiple_optout_keywords(
        self,
        test_client,
        db_session,
        test_phone_number,
        keyword
    ):
        """Test that all opt-out keywords work (case-insensitive)."""
        phone_hash = PhoneHasher.hash_phone(test_phone_number)

        # Send opt-out keyword
        request_data = self.create_twilio_request(test_phone_number, keyword)
        response = test_client.post("/api/webhook/sms", data=request_data)

        # Verify opt-out response
        assert response.status_code == 200
        assert b"unsubscribed" in response.content.lower()

        # Verify opt-out record created
        optout = db_session.query(OptOut).filter(
            OptOut.phone_hash == phone_hash
        ).first()
        assert optout is not None
