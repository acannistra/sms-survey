"""Twilio webhook endpoint for processing incoming SMS messages.

This module handles incoming SMS messages from Twilio webhooks, manages
survey sessions, processes user input, and generates TwiML responses.
"""

from typing import Annotated
from fastapi import APIRouter, Depends, Form, Response
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.session import SurveySession
from app.models.optout import OptOut
from app.schemas.twilio import TwilioWebhookRequest
from app.services.phone_hasher import PhoneHasher
from app.services.survey_loader import get_survey_loader, SurveyNotFoundError
from app.services.survey_engine import SurveyEngine, SurveyEngineError
from app.services.twilio_client import TwilioClient
from app.config import get_settings
from app.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter()

# Opt-out keywords (case-insensitive)
OPT_OUT_KEYWORDS = {"stop", "stopall", "unsubscribe", "cancel", "end", "quit"}


async def parse_twilio_webhook(
    MessageSid: Annotated[str, Form()],
    AccountSid: Annotated[str, Form()],
    From: Annotated[str, Form()],
    To: Annotated[str, Form()],
    Body: Annotated[str, Form()],
    NumMedia: Annotated[str, Form()] = "0"
) -> TwilioWebhookRequest:
    """Parse Twilio form data into TwilioWebhookRequest model.

    Args:
        MessageSid: Twilio message ID
        AccountSid: Twilio account ID
        From: Sender phone number
        To: Recipient phone number
        Body: SMS message text
        NumMedia: Number of media attachments

    Returns:
        TwilioWebhookRequest: Validated webhook request

    Raises:
        ValidationError: If request data is invalid
    """
    return TwilioWebhookRequest(
        MessageSid=MessageSid,
        AccountSid=AccountSid,
        From=From,
        To=To,
        Body=Body,
        NumMedia=NumMedia
    )


def handle_optout_optin(
    db: Session,
    phone_hash: str,
    truncated_hash: str,
    body_lower: str,
    original_body: str,
    survey_id: str,
    response: Response
) -> Response | None:
    """Handle opt-out and opt-in keywords.

    Checks if the message contains opt-out keywords (STOP, etc.) or opt-in
    keywords (START), and handles them appropriately.

    Args:
        db: Database session
        phone_hash: Hashed phone number
        truncated_hash: Truncated hash for logging
        body_lower: Lowercase message body
        original_body: Original message body
        survey_id: Survey ID for welcome message
        response: FastAPI Response object to modify

    Returns:
        Response object if opt-out/opt-in was handled, None otherwise
    """
    # Check for opt-out keywords
    if body_lower in OPT_OUT_KEYWORDS:
        logger.info(f"Opt-out keyword detected from {truncated_hash}: {body_lower}")

        # Add to opt-out list
        OptOut.add_optout(db, phone_hash, original_body)
        db.commit()

        # Return opt-out confirmation
        twiml = TwilioClient.create_response(
            "You have been unsubscribed from SMS notifications. "
            "Text START to opt back in."
        )
        response.media_type = "application/xml"
        response.body = twiml.encode()
        return response

    # Check if user has opted out
    if OptOut.is_opted_out(db, phone_hash):
        logger.info(f"Message from opted-out user {truncated_hash}")

        # Check for opt-in keyword
        if body_lower == "start":
            # Remove from opt-out list
            OptOut.remove_optout(db, phone_hash)
            db.commit()
            logger.info(f"User {truncated_hash} opted back in")

            # Return welcome message
            twiml = TwilioClient.create_response(
                "Welcome back! You have opted back in to SMS notifications. "
                f"Text {survey_id.upper().replace('_', ' ')} to start a survey."
            )
            response.media_type = "application/xml"
            response.body = twiml.encode()
            return response
        else:
            # User is opted out - send empty response
            twiml = TwilioClient.create_empty_response()
            response.media_type = "application/xml"
            response.body = twiml.encode()
            return response

    # No opt-out/opt-in handling needed
    return None


@router.post("/api/webhook/sms")
async def sms_webhook(
    response: Response,
    webhook_request: Annotated[TwilioWebhookRequest, Depends(parse_twilio_webhook)],
    db: Session = Depends(get_db)
) -> Response:
    """Process incoming SMS message from Twilio.

    This endpoint receives SMS messages from Twilio, processes them through
    the survey engine, and returns TwiML responses.

    Flow:
    1. Hash phone number immediately
    2. Check for opt-out keywords
    3. Check if user has opted out
    4. Load survey and detect start words
    5. Create or retrieve session with pessimistic locking
    6. Process message through survey engine
    7. Return TwiML response

    Args:
        response: FastAPI Response object for setting content type
        webhook_request: Validated Twilio webhook request
        db: Database session

    Returns:
        Response: TwiML XML response for Twilio

    Note:
        Phone numbers are hashed immediately and never stored in plaintext.
        All logging uses truncated hashes only.
    """
    settings = get_settings()
    survey_id = settings.default_survey_id

    # Hash phone number immediately
    phone_hash = PhoneHasher.hash_phone(webhook_request.From)
    truncated_hash = PhoneHasher.truncate_for_logging(phone_hash)

    logger.info(
        f"Received SMS from {truncated_hash}: "
        f"MessageSid={webhook_request.MessageSid}, Body={webhook_request.Body[:50]}"
    )

    try:
        # Handle opt-out/opt-in keywords
        body_lower = webhook_request.Body.strip().lower()
        optout_response = handle_optout_optin(
            db, phone_hash, truncated_hash, body_lower,
            webhook_request.Body, survey_id, response
        )
        if optout_response is not None:
            return optout_response

        # Load survey (cached by survey_loader for performance)
        survey_loader = get_survey_loader()
        try:
            survey = survey_loader.load_survey(survey_id)
        except SurveyNotFoundError:
            logger.error(f"Survey not found: {survey_id}")
            twiml = TwilioClient.create_response(
                "Sorry, the survey is temporarily unavailable or closed. Thank you for your participation!"
            )
            response.media_type = "application/xml"
            response.body = twiml.encode()
            return response

        # Check for start words (case-insensitive)
        is_start_word = body_lower in [word.lower() for word in survey.metadata.start_words]

        if is_start_word:
            logger.info(f"Start word detected from {truncated_hash}: {body_lower}")

            # Abandon any existing active sessions
            existing_sessions = db.query(SurveySession).filter(
                SurveySession.phone_hash == phone_hash,
                SurveySession.survey_id == survey_id,
                SurveySession.completed_at.is_(None)
            ).all()

            for session in existing_sessions:
                session.mark_completed()
                logger.info(f"Abandoned existing session {session.id} for {truncated_hash}")

            # Create new session
            new_session = SurveySession(
                phone_hash=phone_hash,
                survey_id=survey_id,
                survey_version=settings.git_commit_sha,
                current_step=survey.consent.step_id,
                consent_given=False,
                context={}
            )
            db.add(new_session)
            db.commit()
            db.refresh(new_session)

            logger.info(f"Created new session {new_session.id} for {truncated_hash}")

            # Return consent message
            twiml = TwilioClient.create_response(survey.consent.text)
            response.media_type = "application/xml"
            response.body = twiml.encode()
            return response

        # Retrieve active session with pessimistic locking
        session = db.query(SurveySession).filter(
            SurveySession.phone_hash == phone_hash,
            SurveySession.survey_id == survey_id,
            SurveySession.completed_at.is_(None)
        ).with_for_update().first()

        if session is None:
            # No active session and not a start word - ignore message
            logger.info(f"No active session for {truncated_hash}, ignoring message")
            twiml = TwilioClient.create_empty_response()
            response.media_type = "application/xml"
            response.body = twiml.encode()
            return response

        # Process message through survey engine
        engine = SurveyEngine(db)
        try:
            response_text, is_completed = engine.process_message(session, webhook_request.Body)

            logger.info(
                f"Processed message for session {session.id}: "
                f"completed={is_completed}, step={session.current_step}"
            )

            # Generate TwiML response
            twiml = TwilioClient.create_response(response_text)
            response.media_type = "application/xml"
            response.body = twiml.encode()
            return response

        except SurveyEngineError as e:
            logger.error(f"Survey engine error for session {session.id}: {e}")
            db.rollback()

            # Return error message
            twiml = TwilioClient.create_response(
                "Sorry, there was an error processing your response. Please try again."
            )
            response.media_type = "application/xml"
            response.body = twiml.encode()
            return response

    except Exception as e:
        logger.error(f"Unexpected error processing webhook: {e}", exc_info=True)
        db.rollback()

        # Return generic error message
        try:
            twiml = TwilioClient.create_response(
                "Sorry, an unexpected error occurred. Please try again later."
            )
            response.media_type = "application/xml"
            response.body = twiml.encode()
        except Exception:
            # Fallback if TwiML generation fails
            response.media_type = "application/xml"
            response.body = b'<?xml version="1.0" encoding="UTF-8"?><Response />'

        return response
