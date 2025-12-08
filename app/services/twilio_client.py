"""Twilio client service for TwiML response generation.

This module provides utilities for generating TwiML (Twilio Markup Language)
responses that control how Twilio handles SMS messages.
"""

from twilio.twiml.messaging_response import MessagingResponse
from app.logging_config import get_logger


logger = get_logger(__name__)


class TwilioClient:
    """Service for generating Twilio TwiML responses.

    TwiML (Twilio Markup Language) is XML that tells Twilio how to respond
    to incoming calls and messages. This service provides static methods
    for generating properly formatted TwiML responses.

    All methods are static since TwiML generation is stateless and does not
    require configuration or instance state.

    Usage:
        from app.services.twilio_client import TwilioClient

        # Generate response with message
        twiml = TwilioClient.create_response("Thanks for your response!")

        # Generate empty response (no message sent)
        twiml = TwilioClient.create_empty_response()
    """

    @staticmethod
    def create_response(message: str) -> str:
        """Generate TwiML response with a message.

        Creates a TwiML MessagingResponse that instructs Twilio to send
        the specified message back to the user.

        Args:
            message: Text message to send to user (max 1600 characters per Twilio)

        Returns:
            TwiML XML string

        Raises:
            ValueError: If message is empty or exceeds Twilio's length limit

        Example:
            >>> twiml = TwilioClient.create_response("What is your name?")
            >>> print(twiml)
            <?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Message>What is your name?</Message>
            </Response>

        Notes:
            - Twilio enforces a 1600 character limit per SMS segment
            - Messages longer than 160 characters are sent as multiple segments
            - This method validates against the 1600 character limit
        """
        # Validate message
        if not message or not message.strip():
            raise ValueError("Message cannot be empty")

        # Twilio's maximum message length
        MAX_MESSAGE_LENGTH = 1600
        if len(message) > MAX_MESSAGE_LENGTH:
            logger.warning(
                f"Message length ({len(message)}) exceeds Twilio limit ({MAX_MESSAGE_LENGTH}). "
                "Message will be truncated."
            )
            message = message[:MAX_MESSAGE_LENGTH]

        # Create TwiML response
        response = MessagingResponse()
        response.message(message)

        logger.debug(f"Generated TwiML response with message: {message[:50]}...")

        return str(response)

    @staticmethod
    def create_empty_response() -> str:
        """Generate empty TwiML response.

        Creates a TwiML response with no message. Useful when we've
        received the message but don't want to send a reply (e.g.,
        after opt-out, duplicate messages, or rate limiting).

        Returns:
            Empty TwiML XML string

        Example:
            >>> twiml = TwilioClient.create_empty_response()
            >>> print(twiml)
            <?xml version="1.0" encoding="UTF-8"?>
            <Response />

        Notes:
            - This acknowledges receipt to Twilio without sending SMS
            - Prevents Twilio from retrying webhook delivery
            - Use for opt-outs, duplicates, or when no response is needed
        """
        response = MessagingResponse()

        logger.debug("Generated empty TwiML response")

        return str(response)

    @staticmethod
    def validate_twiml(twiml_str: str) -> bool:
        """Validate TwiML XML structure.

        Performs basic validation to ensure the TwiML string is well-formed XML
        and contains required elements. This is primarily used for testing.

        Args:
            twiml_str: TwiML XML string to validate

        Returns:
            True if TwiML is valid, False otherwise

        Example:
            >>> twiml = TwilioClient.create_response("Hello")
            >>> TwilioClient.validate_twiml(twiml)
            True
        """
        try:
            # Check for XML declaration
            if not twiml_str.startswith('<?xml version="1.0"'):
                return False

            # Check for Response element
            if '<Response' not in twiml_str:
                return False

            # Check for proper closing
            if '</Response>' not in twiml_str and '/>' not in twiml_str:
                return False

            return True
        except Exception as e:
            logger.error(f"TwiML validation failed: {e}")
            return False
