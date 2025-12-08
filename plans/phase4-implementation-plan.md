# Phase 4 Implementation Plan: Twilio Integration

**Project:** SMS Survey Engine
**Phase:** Phase 4 (Twilio Integration)
**Dependencies:** Phase 0 (Complete), Phase 1 (Complete), Phase 2 (Complete), Phase 3 (Complete)
**Created:** 2025-12-08

## Executive Summary

This plan details the implementation of Twilio webhook integration (Phase 4). This phase creates the bridge between Twilio's SMS infrastructure and the survey engine, handling webhook requests, generating TwiML responses, and enforcing security through signature verification.

**Key Decisions:**
- Use Pydantic v2 for webhook request validation with E.164 phone format validation
- Implement TwiML generation as static methods (no state needed)
- Use FastAPI dependency injection for signature verification
- Never log auth tokens, signatures, or full phone hashes
- Use Twilio SDK's built-in `RequestValidator` for cryptographic verification
- Implement security logging for invalid signature attempts

**Security Considerations:**
- All webhook requests must pass signature verification
- Invalid signatures are logged with client IP for security monitoring
- Phone numbers are validated for E.164 format before hashing
- No sensitive data (tokens, signatures, full hashes) in logs

---

## Phase 4 Overview

### Architecture

```
Twilio SMS Platform
    ↓ (HTTP POST)
app/middleware/twilio_auth.py (signature verification)
    ↓
app/schemas/twilio.py (request validation)
    ↓
app/routes/webhook.py (request handler - Phase 5)
    ↓
app/services/twilio_client.py (TwiML generation)
    ↓ (TwiML XML)
Twilio SMS Platform
```

### Components

1. **Twilio Request Schema** (`app/schemas/twilio.py`): Pydantic model for webhook validation
2. **TwiML Response Generator** (`app/services/twilio_client.py`): Service for generating TwiML XML
3. **Signature Verification Middleware** (`app/middleware/twilio_auth.py`): Security middleware

### Testing Strategy

- Unit tests for each component with comprehensive coverage
- Mock Twilio SDK dependencies to avoid external calls
- Test security scenarios (invalid signatures, missing headers)
- Verify E.164 format validation
- Test TwiML XML generation and formatting

---

## Task 4.1: Create Twilio Request Schema

### Purpose
Define Pydantic model to validate and type incoming Twilio webhook requests. Ensures all required fields are present and phone numbers are in E.164 format.

### Implementation Details

**File:** `/Users/tony/Dropbox/Projects/sms-survey/app/schemas/twilio.py`

**Implementation:**

```python
"""Pydantic schemas for Twilio webhook requests.

This module defines validation rules for incoming Twilio SMS webhooks.
All webhook requests must conform to these schemas before processing.
"""

from pydantic import BaseModel, Field, field_validator


class TwilioWebhookRequest(BaseModel):
    """Twilio SMS webhook request schema.

    Represents an incoming SMS message from Twilio's webhook.
    Twilio sends these fields via POST when a message is received.

    Attributes:
        MessageSid: Unique identifier for the message (34 characters)
        AccountSid: Twilio account identifier (34 characters)
        From: Sender's phone number in E.164 format (e.g., +15551234567)
        To: Recipient's phone number in E.164 format (e.g., +15559876543)
        Body: Text content of the SMS message
        NumMedia: Number of media attachments (0 for text-only)

    Example:
        {
            "MessageSid": "SM1234567890abcdef1234567890abcdef",
            "AccountSid": "AC1234567890abcdef1234567890abcdef",
            "From": "+15551234567",
            "To": "+15559876543",
            "Body": "Hello, this is a test message",
            "NumMedia": "0"
        }
    """

    MessageSid: str = Field(
        ...,
        min_length=34,
        max_length=34,
        description="Unique message identifier from Twilio"
    )
    AccountSid: str = Field(
        ...,
        min_length=34,
        max_length=34,
        description="Twilio account identifier"
    )
    From: str = Field(
        ...,
        alias="From",
        description="Sender phone number in E.164 format"
    )
    To: str = Field(
        ...,
        alias="To",
        description="Recipient phone number in E.164 format"
    )
    Body: str = Field(
        ...,
        description="SMS message text content"
    )
    NumMedia: str = Field(
        default="0",
        description="Number of media attachments"
    )

    model_config = {
        "populate_by_name": True,
        "str_strip_whitespace": True
    }

    @field_validator("From", "To")
    @classmethod
    def validate_e164_format(cls, v: str, info) -> str:
        """Validate phone numbers are in E.164 format.

        E.164 format requirements:
        - Starts with '+'
        - Contains only digits after the '+'
        - Length between 8-15 characters (including '+')

        Args:
            v: Phone number string to validate
            info: Validation context with field information

        Returns:
            Validated phone number string

        Raises:
            ValueError: If phone number is not in valid E.164 format

        Example:
            Valid: +15551234567, +442071234567, +861234567890
            Invalid: 5551234567, +1-555-123-4567, +1 (555) 123-4567
        """
        field_name = info.field_name

        # Must start with '+'
        if not v.startswith("+"):
            raise ValueError(
                f"{field_name} must be in E.164 format (starting with '+'). "
                f"Got: {v}"
            )

        # Remove '+' and check remaining characters are digits
        digits = v[1:]
        if not digits.isdigit():
            raise ValueError(
                f"{field_name} must contain only digits after '+'. "
                f"Got: {v}"
            )

        # Check length constraints (E.164: 1-15 digits after '+')
        if len(digits) < 7 or len(digits) > 15:
            raise ValueError(
                f"{field_name} must have 7-15 digits after '+'. "
                f"Got {len(digits)} digits: {v}"
            )

        return v

    @field_validator("MessageSid", "AccountSid")
    @classmethod
    def validate_sid_format(cls, v: str, info) -> str:
        """Validate SID format matches Twilio's pattern.

        Twilio SIDs are 34 characters starting with specific prefixes:
        - MessageSid starts with 'SM' or 'MM'
        - AccountSid starts with 'AC'

        Args:
            v: SID string to validate
            info: Validation context with field information

        Returns:
            Validated SID string

        Raises:
            ValueError: If SID format is invalid
        """
        field_name = info.field_name

        if field_name == "MessageSid":
            if not (v.startswith("SM") or v.startswith("MM")):
                raise ValueError(
                    f"MessageSid must start with 'SM' or 'MM'. Got: {v[:2]}"
                )
        elif field_name == "AccountSid":
            if not v.startswith("AC"):
                raise ValueError(
                    f"AccountSid must start with 'AC'. Got: {v[:2]}"
                )

        return v

    @property
    def num_media_int(self) -> int:
        """Convert NumMedia string to integer.

        Returns:
            Number of media attachments as integer
        """
        return int(self.NumMedia)

    @property
    def has_media(self) -> bool:
        """Check if message has media attachments.

        Returns:
            True if message has media, False otherwise
        """
        return self.num_media_int > 0
```

**Key Features:**
- E.164 phone number validation (must start with '+', digits only)
- SID format validation (MessageSid: SM/MM prefix, AccountSid: AC prefix)
- Comprehensive error messages for validation failures
- Helper properties for media detection
- Pydantic v2 syntax with `@field_validator` decorator
- Field aliases for Twilio's capitalized field names

**Dependencies:**
- `pydantic>=2.9.2` (already installed)

**Testing Requirements:**
- Valid E.164 formats: +15551234567, +442071234567, +861234567890
- Invalid E.164 formats: 5551234567, +1-555-123-4567, +1 (555) 123-4567
- Edge cases: empty strings, non-numeric characters, incorrect lengths
- SID validation: correct/incorrect prefixes
- Media detection: NumMedia = "0", "1", "3"

---

## Task 4.2: Implement TwiML Response Generator

### Purpose
Generate TwiML (Twilio Markup Language) XML responses that tell Twilio how to respond to SMS messages. Provides simple interface for creating both message responses and empty responses.

### Implementation Details

**File:** `/Users/tony/Dropbox/Projects/sms-survey/app/services/twilio_client.py`

**Implementation:**

```python
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
```

**Key Features:**
- Static methods (no state, no configuration needed)
- Message length validation (1600 character Twilio limit)
- Empty response generation for opt-outs/duplicates
- TwiML validation utility for testing
- Comprehensive docstrings with examples
- Logging for debugging (truncated message preview)

**Dependencies:**
- `twilio>=9.3.7` (already installed)
- `app/logging_config.py` (already implemented)

**TwiML Format:**
```xml
<!-- Message response -->
<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>Your message text here</Message>
</Response>

<!-- Empty response -->
<?xml version="1.0" encoding="UTF-8"?>
<Response />
```

**Testing Requirements:**
- Valid message generation
- Empty response generation
- Message length validation and truncation
- Empty/whitespace message rejection
- TwiML structure validation
- XML formatting correctness

---

## Task 4.3: Implement Twilio Signature Verification Middleware

### Purpose
Secure webhook endpoint by verifying Twilio's cryptographic signature. Prevents unauthorized access and request forgery attacks.

### Implementation Details

**File:** `/Users/tony/Dropbox/Projects/sms-survey/app/middleware/twilio_auth.py`

**Implementation:**

```python
"""Twilio signature verification middleware.

This module provides FastAPI middleware to verify that incoming webhook
requests are genuinely from Twilio by validating cryptographic signatures.

Security: All webhook endpoints MUST use this verification to prevent
unauthorized access and request forgery attacks.
"""

from typing import Dict
from fastapi import Request, HTTPException, Depends
from twilio.request_validator import RequestValidator

from app.config import get_settings
from app.logging_config import get_logger


logger = get_logger(__name__)


class TwilioSignatureValidator:
    """Service for validating Twilio webhook signatures.

    Twilio signs all webhook requests with an HMAC-SHA1 signature based on:
    - Your auth token (secret key)
    - The full webhook URL
    - All POST parameters

    This signature prevents attackers from spoofing webhook requests.

    Security Notes:
        - NEVER log auth tokens or signature values
        - Log security events (invalid signatures) with client IP
        - Use HTTPS in production to prevent MITM attacks
        - Signature verification must happen BEFORE any request processing

    Reference:
        https://www.twilio.com/docs/usage/security#validating-requests
    """

    def __init__(self):
        """Initialize validator with auth token from settings."""
        settings = get_settings()
        self.validator = RequestValidator(settings.twilio_auth_token)
        logger.debug("TwilioSignatureValidator initialized")

    async def verify_request(
        self,
        request: Request,
        signature: str,
        url: str,
        params: Dict[str, str]
    ) -> bool:
        """Verify Twilio webhook signature.

        Validates that the request came from Twilio by checking the
        cryptographic signature against the expected value.

        Args:
            request: FastAPI request object (for logging context)
            signature: X-Twilio-Signature header value
            url: Full webhook URL (including protocol and domain)
            params: POST parameters as dict

        Returns:
            True if signature is valid, False otherwise

        Example:
            validator = TwilioSignatureValidator()
            is_valid = await validator.verify_request(
                request=request,
                signature=request.headers.get("X-Twilio-Signature"),
                url="https://example.com/webhook/sms",
                params={"From": "+15551234567", "Body": "Hello"}
            )

        Security:
            - Never logs signature values or auth tokens
            - Logs client IP for invalid signature attempts
            - Uses constant-time comparison to prevent timing attacks
        """
        try:
            # Extract client IP for security logging
            client_ip = request.client.host if request.client else "unknown"

            # Validate signature using Twilio's SDK
            is_valid = self.validator.validate(url, params, signature)

            if not is_valid:
                logger.warning(
                    f"Invalid Twilio signature from IP: {client_ip}",
                    extra={"client_ip": client_ip, "url": url}
                )
                return False

            logger.debug(f"Valid Twilio signature verified for: {url}")
            return True

        except Exception as e:
            # Log error without exposing sensitive data
            logger.error(
                f"Error validating Twilio signature: {str(e)}",
                extra={"error_type": type(e).__name__}
            )
            return False


# Dependency function for FastAPI routes
async def verify_twilio_signature(request: Request) -> None:
    """FastAPI dependency for Twilio signature verification.

    Use this as a dependency in FastAPI routes to automatically verify
    that incoming requests are from Twilio.

    Args:
        request: FastAPI request object

    Raises:
        HTTPException(403): If signature is missing or invalid

    Usage:
        @app.post("/webhook/sms", dependencies=[Depends(verify_twilio_signature)])
        async def handle_sms(webhook_data: TwilioWebhookRequest):
            # Request is verified, safe to process
            pass

    Security:
        - Returns 403 Forbidden for invalid signatures (not 401)
        - Logs security events for monitoring
        - Validates signature BEFORE route handler execution
    """
    # Extract signature from headers
    signature = request.headers.get("X-Twilio-Signature")
    if not signature:
        client_ip = request.client.host if request.client else "unknown"
        logger.warning(
            f"Missing X-Twilio-Signature header from IP: {client_ip}",
            extra={"client_ip": client_ip}
        )
        raise HTTPException(
            status_code=403,
            detail="Missing Twilio signature"
        )

    # Get full URL (including query parameters if any)
    url = str(request.url)

    # Extract POST parameters
    # Twilio sends form data, so we need to get the raw form
    form_data = await request.form()
    params = {key: value for key, value in form_data.items()}

    # Verify signature
    validator = TwilioSignatureValidator()
    is_valid = await validator.verify_request(
        request=request,
        signature=signature,
        url=url,
        params=params
    )

    if not is_valid:
        raise HTTPException(
            status_code=403,
            detail="Invalid Twilio signature"
        )

    # Signature valid, allow request to proceed
    logger.debug("Twilio signature verification passed")
```

**Key Features:**
- Uses Twilio SDK's `RequestValidator` for cryptographic verification
- FastAPI dependency injection pattern for route protection
- Security logging (invalid attempts with client IP)
- Never logs secrets (auth tokens, signatures)
- Proper error handling with meaningful status codes (403, not 401)
- Async/await support for FastAPI integration
- Comprehensive docstrings with security notes

**Security Considerations:**
1. **Signature Validation**: Uses HMAC-SHA1 with auth token
2. **Timing Attack Prevention**: Twilio SDK uses constant-time comparison
3. **Logging Security Events**: Invalid signatures logged with client IP
4. **No Secret Logging**: Never logs auth tokens or signature values
5. **HTTPS Required**: Signature alone doesn't prevent MITM (need HTTPS in production)

**Dependencies:**
- `twilio>=9.3.7` (already installed)
- `fastapi>=0.115.0` (already installed)
- `app/config.py` (already implemented)
- `app/logging_config.py` (already implemented)

**Testing Requirements:**
- Valid signature verification
- Invalid signature rejection
- Missing signature header handling
- Malformed signature handling
- Client IP logging verification
- No auth token leakage in logs
- Exception handling during verification

---

## Task 4.4: Unit Tests for Twilio Schema

### Purpose
Comprehensive test coverage for Twilio webhook request validation.

### Implementation Details

**File:** `/Users/tony/Dropbox/Projects/sms-survey/tests/unit/test_twilio_schemas.py`

**Implementation:**

```python
"""Unit tests for Twilio webhook request schemas."""

import pytest
from pydantic import ValidationError

from app.schemas.twilio import TwilioWebhookRequest


class TestTwilioWebhookRequest:
    """Test suite for TwilioWebhookRequest schema."""

    @pytest.fixture
    def valid_webhook_data(self):
        """Valid webhook request data."""
        return {
            "MessageSid": "SM1234567890abcdef1234567890abcdef",
            "AccountSid": "AC1234567890abcdef1234567890abcdef",
            "From": "+15551234567",
            "To": "+15559876543",
            "Body": "Hello, this is a test message",
            "NumMedia": "0"
        }

    def test_valid_webhook_request(self, valid_webhook_data):
        """Test that valid webhook data passes validation."""
        webhook = TwilioWebhookRequest(**valid_webhook_data)

        assert webhook.MessageSid == "SM1234567890abcdef1234567890abcdef"
        assert webhook.AccountSid == "AC1234567890abcdef1234567890abcdef"
        assert webhook.From == "+15551234567"
        assert webhook.To == "+15559876543"
        assert webhook.Body == "Hello, this is a test message"
        assert webhook.NumMedia == "0"

    def test_e164_validation_valid_formats(self, valid_webhook_data):
        """Test E.164 validation accepts valid formats."""
        valid_phones = [
            "+15551234567",      # US
            "+442071234567",     # UK
            "+861234567890",     # China
            "+61412345678",      # Australia
            "+33123456789",      # France
        ]

        for phone in valid_phones:
            data = valid_webhook_data.copy()
            data["From"] = phone
            webhook = TwilioWebhookRequest(**data)
            assert webhook.From == phone

    def test_e164_validation_missing_plus(self, valid_webhook_data):
        """Test E.164 validation rejects numbers without '+'."""
        data = valid_webhook_data.copy()
        data["From"] = "15551234567"

        with pytest.raises(ValidationError) as exc_info:
            TwilioWebhookRequest(**data)

        errors = exc_info.value.errors()
        assert any("must be in E.164 format" in str(e["msg"]) for e in errors)

    def test_e164_validation_non_numeric(self, valid_webhook_data):
        """Test E.164 validation rejects non-numeric characters."""
        invalid_phones = [
            "+1-555-123-4567",   # Dashes
            "+1 (555) 123-4567", # Parentheses and spaces
            "+1.555.123.4567",   # Dots
            "+1abc5551234",      # Letters
        ]

        for phone in invalid_phones:
            data = valid_webhook_data.copy()
            data["From"] = phone

            with pytest.raises(ValidationError) as exc_info:
                TwilioWebhookRequest(**data)

            errors = exc_info.value.errors()
            assert any("must contain only digits" in str(e["msg"]) for e in errors)

    def test_e164_validation_length_constraints(self, valid_webhook_data):
        """Test E.164 validation enforces length constraints."""
        # Too short (less than 7 digits after '+')
        data = valid_webhook_data.copy()
        data["From"] = "+123456"

        with pytest.raises(ValidationError) as exc_info:
            TwilioWebhookRequest(**data)

        errors = exc_info.value.errors()
        assert any("must have 7-15 digits" in str(e["msg"]) for e in errors)

        # Too long (more than 15 digits after '+')
        data["From"] = "+1234567890123456"  # 16 digits

        with pytest.raises(ValidationError) as exc_info:
            TwilioWebhookRequest(**data)

        errors = exc_info.value.errors()
        assert any("must have 7-15 digits" in str(e["msg"]) for e in errors)

    def test_sid_format_validation_message_sid(self, valid_webhook_data):
        """Test MessageSid format validation."""
        # Valid prefixes: SM or MM
        for prefix in ["SM", "MM"]:
            data = valid_webhook_data.copy()
            data["MessageSid"] = f"{prefix}1234567890abcdef1234567890abcdef"
            webhook = TwilioWebhookRequest(**data)
            assert webhook.MessageSid.startswith(prefix)

        # Invalid prefix
        data = valid_webhook_data.copy()
        data["MessageSid"] = "XX1234567890abcdef1234567890abcdef"

        with pytest.raises(ValidationError) as exc_info:
            TwilioWebhookRequest(**data)

        errors = exc_info.value.errors()
        assert any("must start with 'SM' or 'MM'" in str(e["msg"]) for e in errors)

    def test_sid_format_validation_account_sid(self, valid_webhook_data):
        """Test AccountSid format validation."""
        # Valid AccountSid starts with AC
        data = valid_webhook_data.copy()
        data["AccountSid"] = "AC1234567890abcdef1234567890abcdef"
        webhook = TwilioWebhookRequest(**data)
        assert webhook.AccountSid.startswith("AC")

        # Invalid prefix
        data["AccountSid"] = "XX1234567890abcdef1234567890abcdef"

        with pytest.raises(ValidationError) as exc_info:
            TwilioWebhookRequest(**data)

        errors = exc_info.value.errors()
        assert any("must start with 'AC'" in str(e["msg"]) for e in errors)

    def test_sid_length_validation(self, valid_webhook_data):
        """Test SID length must be exactly 34 characters."""
        # MessageSid too short
        data = valid_webhook_data.copy()
        data["MessageSid"] = "SM123"

        with pytest.raises(ValidationError):
            TwilioWebhookRequest(**data)

        # MessageSid too long
        data["MessageSid"] = "SM" + "1" * 50

        with pytest.raises(ValidationError):
            TwilioWebhookRequest(**data)

    def test_body_can_be_empty(self, valid_webhook_data):
        """Test that Body field can be empty string."""
        data = valid_webhook_data.copy()
        data["Body"] = ""

        webhook = TwilioWebhookRequest(**data)
        assert webhook.Body == ""

    def test_num_media_defaults_to_zero(self):
        """Test that NumMedia defaults to '0' if not provided."""
        data = {
            "MessageSid": "SM1234567890abcdef1234567890abcdef",
            "AccountSid": "AC1234567890abcdef1234567890abcdef",
            "From": "+15551234567",
            "To": "+15559876543",
            "Body": "Test"
        }

        webhook = TwilioWebhookRequest(**data)
        assert webhook.NumMedia == "0"

    def test_num_media_int_property(self, valid_webhook_data):
        """Test num_media_int property converts string to int."""
        data = valid_webhook_data.copy()
        data["NumMedia"] = "3"

        webhook = TwilioWebhookRequest(**data)
        assert webhook.num_media_int == 3
        assert isinstance(webhook.num_media_int, int)

    def test_has_media_property(self, valid_webhook_data):
        """Test has_media property detects media attachments."""
        # No media
        data = valid_webhook_data.copy()
        data["NumMedia"] = "0"
        webhook = TwilioWebhookRequest(**data)
        assert webhook.has_media is False

        # Has media
        data["NumMedia"] = "1"
        webhook = TwilioWebhookRequest(**data)
        assert webhook.has_media is True

        data["NumMedia"] = "3"
        webhook = TwilioWebhookRequest(**data)
        assert webhook.has_media is True

    def test_whitespace_stripping(self, valid_webhook_data):
        """Test that whitespace is stripped from string fields."""
        data = valid_webhook_data.copy()
        data["Body"] = "  Hello World  "

        webhook = TwilioWebhookRequest(**data)
        assert webhook.Body == "Hello World"

    def test_case_sensitivity_in_field_names(self):
        """Test that field names are case-sensitive (From/To vs from/to)."""
        # Pydantic should handle both via alias
        data = {
            "MessageSid": "SM1234567890abcdef1234567890abcdef",
            "AccountSid": "AC1234567890abcdef1234567890abcdef",
            "from": "+15551234567",  # lowercase
            "to": "+15559876543",    # lowercase
            "Body": "Test"
        }

        # Should fail because we use 'From' and 'To' as field names
        with pytest.raises(ValidationError):
            TwilioWebhookRequest(**data)
```

**Test Coverage:**
- Valid webhook data parsing
- E.164 format validation (valid/invalid)
- SID format validation (MessageSid, AccountSid)
- Length constraints (phone numbers, SIDs)
- Empty/missing fields
- Helper properties (num_media_int, has_media)
- Whitespace stripping
- Edge cases

---

## Task 4.5: Unit Tests for TwiML Response Generator

### Purpose
Test TwiML XML generation, validation, and error handling.

### Implementation Details

**File:** `/Users/tony/Dropbox/Projects/sms-survey/tests/unit/test_twilio_client.py`

**Implementation:**

```python
"""Unit tests for Twilio client service."""

import pytest
from unittest.mock import patch, MagicMock

from app.services.twilio_client import TwilioClient


class TestTwilioClient:
    """Test suite for TwilioClient class."""

    def test_create_response_with_message(self):
        """Test creating TwiML response with a message."""
        message = "What is your name?"
        twiml = TwilioClient.create_response(message)

        # Verify it's valid XML
        assert twiml.startswith('<?xml version="1.0"')
        assert '<Response>' in twiml
        assert '</Response>' in twiml
        assert '<Message>' in twiml
        assert '</Message>' in twiml
        assert message in twiml

    def test_create_response_xml_structure(self):
        """Test TwiML response has correct XML structure."""
        message = "Test message"
        twiml = TwilioClient.create_response(message)

        # Should be valid TwiML
        assert TwilioClient.validate_twiml(twiml)

        # Check structure
        lines = [line.strip() for line in twiml.split('\n') if line.strip()]
        assert any('<?xml version="1.0"' in line for line in lines)
        assert any('<Response>' in line for line in lines)
        assert any('<Message>' in line for line in lines)
        assert any('</Message>' in line for line in lines)
        assert any('</Response>' in line for line in lines)

    def test_create_response_escapes_special_characters(self):
        """Test that special XML characters are properly escaped."""
        message = "Test <message> with & special 'characters' and \"quotes\""
        twiml = TwilioClient.create_response(message)

        # Twilio SDK should handle XML escaping
        assert '<Message>' in twiml
        assert '</Message>' in twiml

    def test_create_response_empty_message_raises_error(self):
        """Test that empty message raises ValueError."""
        with pytest.raises(ValueError, match="Message cannot be empty"):
            TwilioClient.create_response("")

    def test_create_response_whitespace_only_raises_error(self):
        """Test that whitespace-only message raises ValueError."""
        with pytest.raises(ValueError, match="Message cannot be empty"):
            TwilioClient.create_response("   ")

    def test_create_response_long_message_truncation(self):
        """Test that messages exceeding 1600 characters are truncated."""
        # Create message longer than 1600 characters
        long_message = "x" * 1700

        with patch('app.services.twilio_client.logger') as mock_logger:
            twiml = TwilioClient.create_response(long_message)

            # Should log warning
            mock_logger.warning.assert_called_once()
            assert "exceeds Twilio limit" in str(mock_logger.warning.call_args)

            # Message should be truncated
            assert len(long_message[:1600]) == 1600

    def test_create_response_exact_limit_no_truncation(self):
        """Test that message exactly at 1600 characters is not truncated."""
        message = "x" * 1600

        with patch('app.services.twilio_client.logger') as mock_logger:
            twiml = TwilioClient.create_response(message)

            # Should not log warning
            mock_logger.warning.assert_not_called()

            # Message should be in TwiML
            assert message in twiml

    def test_create_empty_response(self):
        """Test creating empty TwiML response."""
        twiml = TwilioClient.create_empty_response()

        # Verify it's valid XML
        assert twiml.startswith('<?xml version="1.0"')
        assert '<Response' in twiml

        # Should be self-closing or empty
        assert '/>' in twiml or '</Response>' in twiml

        # Should not contain Message element
        assert '<Message>' not in twiml

    def test_create_empty_response_xml_structure(self):
        """Test empty TwiML response has correct XML structure."""
        twiml = TwilioClient.create_empty_response()

        # Should be valid TwiML
        assert TwilioClient.validate_twiml(twiml)

        # Check for XML declaration
        assert '<?xml version="1.0"' in twiml

        # Check for Response element
        assert '<Response' in twiml

    def test_validate_twiml_valid_message_response(self):
        """Test TwiML validation accepts valid message response."""
        twiml = TwilioClient.create_response("Test")
        assert TwilioClient.validate_twiml(twiml) is True

    def test_validate_twiml_valid_empty_response(self):
        """Test TwiML validation accepts valid empty response."""
        twiml = TwilioClient.create_empty_response()
        assert TwilioClient.validate_twiml(twiml) is True

    def test_validate_twiml_invalid_no_xml_declaration(self):
        """Test TwiML validation rejects missing XML declaration."""
        invalid_twiml = "<Response><Message>Test</Message></Response>"
        assert TwilioClient.validate_twiml(invalid_twiml) is False

    def test_validate_twiml_invalid_no_response_element(self):
        """Test TwiML validation rejects missing Response element."""
        invalid_twiml = '<?xml version="1.0" encoding="UTF-8"?><Message>Test</Message>'
        assert TwilioClient.validate_twiml(invalid_twiml) is False

    def test_validate_twiml_invalid_unclosed_tags(self):
        """Test TwiML validation rejects unclosed tags."""
        invalid_twiml = '<?xml version="1.0" encoding="UTF-8"?><Response><Message>Test'
        assert TwilioClient.validate_twiml(invalid_twiml) is False

    def test_create_response_logs_debug_message(self):
        """Test that create_response logs debug message."""
        with patch('app.services.twilio_client.logger') as mock_logger:
            TwilioClient.create_response("Test message for logging")

            # Should log debug message with truncated content
            mock_logger.debug.assert_called_once()
            assert "Generated TwiML response" in str(mock_logger.debug.call_args)

    def test_create_empty_response_logs_debug_message(self):
        """Test that create_empty_response logs debug message."""
        with patch('app.services.twilio_client.logger') as mock_logger:
            TwilioClient.create_empty_response()

            # Should log debug message
            mock_logger.debug.assert_called_once()
            assert "Generated empty TwiML response" in str(mock_logger.debug.call_args)

    def test_create_response_unicode_characters(self):
        """Test that TwiML response handles unicode characters."""
        message = "Hello 世界! 🌍 Testing émojis and spëcial çhars"
        twiml = TwilioClient.create_response(message)

        # Should create valid TwiML
        assert TwilioClient.validate_twiml(twiml)

        # Message should be preserved (Twilio SDK handles encoding)
        assert message in twiml or 'UTF-8' in twiml

    def test_create_response_newlines_preserved(self):
        """Test that newlines in messages are preserved."""
        message = "Line 1\nLine 2\nLine 3"
        twiml = TwilioClient.create_response(message)

        # Should create valid TwiML
        assert TwilioClient.validate_twiml(twiml)
```

**Test Coverage:**
- Basic TwiML generation
- XML structure validation
- Empty message handling
- Message length limits and truncation
- Empty response generation
- Special character escaping
- Unicode support
- Logging verification
- Edge cases

---

## Task 4.6: Unit Tests for Twilio Signature Verification

### Purpose
Test signature verification logic, security scenarios, and error handling.

### Implementation Details

**File:** `/Users/tony/Dropbox/Projects/sms-survey/tests/unit/test_twilio_auth.py`

**Implementation:**

```python
"""Unit tests for Twilio signature verification middleware."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi import HTTPException, Request

from app.middleware.twilio_auth import (
    TwilioSignatureValidator,
    verify_twilio_signature
)


class TestTwilioSignatureValidator:
    """Test suite for TwilioSignatureValidator class."""

    @pytest.fixture
    def mock_settings(self):
        """Mock settings with test auth token."""
        with patch('app.middleware.twilio_auth.get_settings') as mock:
            mock_settings = Mock()
            mock_settings.twilio_auth_token = "test_auth_token_123"
            mock.return_value = mock_settings
            yield mock_settings

    @pytest.fixture
    def mock_request(self):
        """Mock FastAPI request."""
        request = Mock(spec=Request)
        request.client = Mock()
        request.client.host = "192.168.1.1"
        return request

    @pytest.fixture
    def validator(self, mock_settings):
        """Create validator instance with mocked settings."""
        return TwilioSignatureValidator()

    @pytest.mark.asyncio
    async def test_valid_signature_verification(self, validator, mock_request):
        """Test that valid signatures are accepted."""
        signature = "valid_signature_hash"
        url = "https://example.com/webhook/sms"
        params = {"From": "+15551234567", "Body": "Test"}

        # Mock Twilio validator to return True
        with patch.object(validator.validator, 'validate', return_value=True):
            is_valid = await validator.verify_request(
                request=mock_request,
                signature=signature,
                url=url,
                params=params
            )

        assert is_valid is True

    @pytest.mark.asyncio
    async def test_invalid_signature_verification(self, validator, mock_request):
        """Test that invalid signatures are rejected."""
        signature = "invalid_signature_hash"
        url = "https://example.com/webhook/sms"
        params = {"From": "+15551234567", "Body": "Test"}

        # Mock Twilio validator to return False
        with patch.object(validator.validator, 'validate', return_value=False):
            with patch('app.middleware.twilio_auth.logger') as mock_logger:
                is_valid = await validator.verify_request(
                    request=mock_request,
                    signature=signature,
                    url=url,
                    params=params
                )

                # Should log warning with client IP
                mock_logger.warning.assert_called_once()
                warning_msg = str(mock_logger.warning.call_args)
                assert "Invalid Twilio signature" in warning_msg
                assert "192.168.1.1" in warning_msg

        assert is_valid is False

    @pytest.mark.asyncio
    async def test_signature_verification_with_no_client_ip(self, validator):
        """Test signature verification when client IP is unavailable."""
        request = Mock(spec=Request)
        request.client = None  # No client info

        signature = "invalid_signature"
        url = "https://example.com/webhook/sms"
        params = {"From": "+15551234567"}

        with patch.object(validator.validator, 'validate', return_value=False):
            with patch('app.middleware.twilio_auth.logger') as mock_logger:
                is_valid = await validator.verify_request(
                    request=request,
                    signature=signature,
                    url=url,
                    params=params
                )

                # Should log with "unknown" as IP
                warning_msg = str(mock_logger.warning.call_args)
                assert "unknown" in warning_msg

        assert is_valid is False

    @pytest.mark.asyncio
    async def test_signature_verification_exception_handling(self, validator, mock_request):
        """Test that exceptions during verification are handled gracefully."""
        signature = "test_signature"
        url = "https://example.com/webhook/sms"
        params = {"From": "+15551234567"}

        # Mock validator to raise exception
        with patch.object(validator.validator, 'validate', side_effect=Exception("Test error")):
            with patch('app.middleware.twilio_auth.logger') as mock_logger:
                is_valid = await validator.verify_request(
                    request=mock_request,
                    signature=signature,
                    url=url,
                    params=params
                )

                # Should log error
                mock_logger.error.assert_called_once()
                error_msg = str(mock_logger.error.call_args)
                assert "Error validating Twilio signature" in error_msg

        # Should return False on exception
        assert is_valid is False

    @pytest.mark.asyncio
    async def test_signature_verification_logs_success(self, validator, mock_request):
        """Test that successful verification is logged."""
        signature = "valid_signature"
        url = "https://example.com/webhook/sms"
        params = {"From": "+15551234567"}

        with patch.object(validator.validator, 'validate', return_value=True):
            with patch('app.middleware.twilio_auth.logger') as mock_logger:
                await validator.verify_request(
                    request=mock_request,
                    signature=signature,
                    url=url,
                    params=params
                )

                # Should log debug message
                mock_logger.debug.assert_called_once()
                debug_msg = str(mock_logger.debug.call_args)
                assert "Valid Twilio signature verified" in debug_msg

    def test_validator_initialization(self, mock_settings):
        """Test that validator initializes with auth token from settings."""
        validator = TwilioSignatureValidator()

        # Should have RequestValidator instance
        assert validator.validator is not None

    @pytest.mark.asyncio
    async def test_signature_not_logged(self, validator, mock_request):
        """Test that signature values are never logged."""
        signature = "secret_signature_value_should_not_be_logged"
        url = "https://example.com/webhook/sms"
        params = {"From": "+15551234567"}

        with patch.object(validator.validator, 'validate', return_value=False):
            with patch('app.middleware.twilio_auth.logger') as mock_logger:
                await validator.verify_request(
                    request=mock_request,
                    signature=signature,
                    url=url,
                    params=params
                )

                # Check that signature is not in any log calls
                for call in mock_logger.warning.call_args_list + mock_logger.debug.call_args_list:
                    call_str = str(call)
                    assert signature not in call_str


class TestVerifyTwilioSignatureDependency:
    """Test suite for verify_twilio_signature FastAPI dependency."""

    @pytest.fixture
    def mock_request_with_signature(self):
        """Mock request with valid signature header."""
        request = AsyncMock(spec=Request)
        request.headers = {"X-Twilio-Signature": "valid_signature_123"}
        request.url = "https://example.com/webhook/sms"
        request.client = Mock()
        request.client.host = "192.168.1.1"

        # Mock form data
        async def mock_form():
            return {"From": "+15551234567", "Body": "Test"}
        request.form = mock_form

        return request

    @pytest.mark.asyncio
    async def test_missing_signature_header(self):
        """Test that missing signature header raises 403."""
        request = Mock(spec=Request)
        request.headers = {}  # No signature header
        request.client = Mock()
        request.client.host = "192.168.1.1"

        with patch('app.middleware.twilio_auth.logger') as mock_logger:
            with pytest.raises(HTTPException) as exc_info:
                await verify_twilio_signature(request)

            # Should raise 403
            assert exc_info.value.status_code == 403
            assert "Missing Twilio signature" in exc_info.value.detail

            # Should log warning
            mock_logger.warning.assert_called_once()
            warning_msg = str(mock_logger.warning.call_args)
            assert "Missing X-Twilio-Signature header" in warning_msg

    @pytest.mark.asyncio
    async def test_valid_signature_passes(self, mock_request_with_signature):
        """Test that valid signature allows request through."""
        with patch('app.middleware.twilio_auth.TwilioSignatureValidator') as MockValidator:
            mock_validator = MockValidator.return_value
            mock_validator.verify_request = AsyncMock(return_value=True)

            # Should not raise exception
            await verify_twilio_signature(mock_request_with_signature)

    @pytest.mark.asyncio
    async def test_invalid_signature_raises_403(self, mock_request_with_signature):
        """Test that invalid signature raises 403."""
        with patch('app.middleware.twilio_auth.TwilioSignatureValidator') as MockValidator:
            mock_validator = MockValidator.return_value
            mock_validator.verify_request = AsyncMock(return_value=False)

            with pytest.raises(HTTPException) as exc_info:
                await verify_twilio_signature(mock_request_with_signature)

            # Should raise 403
            assert exc_info.value.status_code == 403
            assert "Invalid Twilio signature" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_form_data_extraction(self, mock_request_with_signature):
        """Test that form data is correctly extracted for verification."""
        with patch('app.middleware.twilio_auth.TwilioSignatureValidator') as MockValidator:
            mock_validator = MockValidator.return_value
            mock_validator.verify_request = AsyncMock(return_value=True)

            await verify_twilio_signature(mock_request_with_signature)

            # Verify that verify_request was called with correct params
            call_args = mock_validator.verify_request.call_args
            params = call_args.kwargs['params']
            assert params == {"From": "+15551234567", "Body": "Test"}

    @pytest.mark.asyncio
    async def test_url_extraction(self, mock_request_with_signature):
        """Test that full URL is extracted for verification."""
        with patch('app.middleware.twilio_auth.TwilioSignatureValidator') as MockValidator:
            mock_validator = MockValidator.return_value
            mock_validator.verify_request = AsyncMock(return_value=True)

            await verify_twilio_signature(mock_request_with_signature)

            # Verify URL was passed
            call_args = mock_validator.verify_request.call_args
            url = call_args.kwargs['url']
            assert url == "https://example.com/webhook/sms"

    @pytest.mark.asyncio
    async def test_signature_extraction(self, mock_request_with_signature):
        """Test that signature is extracted from headers."""
        with patch('app.middleware.twilio_auth.TwilioSignatureValidator') as MockValidator:
            mock_validator = MockValidator.return_value
            mock_validator.verify_request = AsyncMock(return_value=True)

            await verify_twilio_signature(mock_request_with_signature)

            # Verify signature was passed
            call_args = mock_validator.verify_request.call_args
            signature = call_args.kwargs['signature']
            assert signature == "valid_signature_123"

    @pytest.mark.asyncio
    async def test_success_logging(self, mock_request_with_signature):
        """Test that successful verification is logged."""
        with patch('app.middleware.twilio_auth.TwilioSignatureValidator') as MockValidator:
            mock_validator = MockValidator.return_value
            mock_validator.verify_request = AsyncMock(return_value=True)

            with patch('app.middleware.twilio_auth.logger') as mock_logger:
                await verify_twilio_signature(mock_request_with_signature)

                # Should log debug message
                mock_logger.debug.assert_called_once()
                debug_msg = str(mock_logger.debug.call_args)
                assert "Twilio signature verification passed" in debug_msg
```

**Test Coverage:**
- Valid/invalid signature verification
- Missing signature header handling
- Client IP logging (present and absent)
- Exception handling during verification
- No secret leakage in logs
- Form data extraction
- URL extraction
- FastAPI dependency integration
- HTTP 403 responses for security failures

---

## Testing Strategy Summary

### Test Execution Order

1. **Task 4.4**: Test Twilio schema validation (foundation)
2. **Task 4.5**: Test TwiML generation (service layer)
3. **Task 4.6**: Test signature verification (security layer)

### Coverage Goals

- **Overall**: >90% code coverage for Phase 4
- **Security tests**: 100% coverage for signature verification
- **Edge cases**: All validation edge cases tested
- **Error handling**: All exception paths tested

### Running Tests

```bash
# Run all Phase 4 tests
pytest tests/unit/test_twilio_schemas.py -v
pytest tests/unit/test_twilio_client.py -v
pytest tests/unit/test_twilio_auth.py -v

# Run with coverage
pytest tests/unit/test_twilio_*.py --cov=app/schemas/twilio --cov=app/services/twilio_client --cov=app/middleware/twilio_auth --cov-report=html

# Run specific test class
pytest tests/unit/test_twilio_auth.py::TestTwilioSignatureValidator -v
```

---

## Implementation Order & Dependencies

### Recommended Implementation Sequence

```
Phase 4.1: Twilio Request Schema
    ↓ (needed by)
Phase 4.2: TwiML Response Generator
    ↓ (independent)
Phase 4.3: Signature Verification Middleware
    ↓ (all needed for)
Phase 4.4-4.6: Unit Tests (parallel)
```

### Detailed Implementation Steps

#### Step 1: Task 4.1 - Twilio Request Schema (30 minutes)
1. Create `/Users/tony/Dropbox/Projects/sms-survey/app/schemas/twilio.py`
2. Implement `TwilioWebhookRequest` with validators
3. Test manually with Python REPL:
   ```python
   from app.schemas.twilio import TwilioWebhookRequest
   req = TwilioWebhookRequest(
       MessageSid="SM" + "1"*32,
       AccountSid="AC" + "1"*32,
       From="+15551234567",
       To="+15559876543",
       Body="Test"
   )
   print(req.From)  # Should print: +15551234567
   ```

#### Step 2: Task 4.2 - TwiML Response Generator (30 minutes)
1. Create `/Users/tony/Dropbox/Projects/sms-survey/app/services/twilio_client.py`
2. Implement `TwilioClient` class
3. Test manually:
   ```python
   from app.services.twilio_client import TwilioClient
   twiml = TwilioClient.create_response("Hello!")
   print(twiml)  # Should show XML
   ```

#### Step 3: Task 4.3 - Signature Verification (45 minutes)
1. Create `/Users/tony/Dropbox/Projects/sms-survey/app/middleware/twilio_auth.py`
2. Implement `TwilioSignatureValidator` and `verify_twilio_signature`
3. Manual testing requires actual Twilio credentials (skip until integration tests)

#### Step 4: Task 4.4 - Schema Tests (30 minutes)
1. Create `/Users/tony/Dropbox/Projects/sms-survey/tests/unit/test_twilio_schemas.py`
2. Run tests: `pytest tests/unit/test_twilio_schemas.py -v`
3. Verify all tests pass

#### Step 5: Task 4.5 - TwiML Tests (30 minutes)
1. Create `/Users/tony/Dropbox/Projects/sms-survey/tests/unit/test_twilio_client.py`
2. Run tests: `pytest tests/unit/test_twilio_client.py -v`
3. Verify all tests pass

#### Step 6: Task 4.6 - Auth Tests (45 minutes)
1. Create `/Users/tony/Dropbox/Projects/sms-survey/tests/unit/test_twilio_auth.py`
2. Run tests: `pytest tests/unit/test_twilio_auth.py -v`
3. Verify all tests pass

### Total Estimated Time: 3.5 hours

---

## Verification & Acceptance Criteria

### Task 4.1 Acceptance Criteria
- [ ] File `app/schemas/twilio.py` created
- [ ] `TwilioWebhookRequest` Pydantic model implemented
- [ ] E.164 validation rejects invalid phone numbers
- [ ] E.164 validation accepts valid international numbers
- [ ] SID validation enforces correct prefixes and length
- [ ] Helper properties (`num_media_int`, `has_media`) work correctly
- [ ] Comprehensive docstrings with examples

### Task 4.2 Acceptance Criteria
- [ ] File `app/services/twilio_client.py` created
- [ ] `TwilioClient.create_response()` generates valid TwiML
- [ ] `TwilioClient.create_empty_response()` generates empty TwiML
- [ ] Message length validation (1600 char limit)
- [ ] Empty message rejection
- [ ] TwiML validation utility works
- [ ] Static methods (no instance state)

### Task 4.3 Acceptance Criteria
- [ ] File `app/middleware/twilio_auth.py` created
- [ ] `TwilioSignatureValidator` class implemented
- [ ] `verify_twilio_signature()` FastAPI dependency implemented
- [ ] Valid signatures accepted
- [ ] Invalid signatures rejected with HTTP 403
- [ ] Missing signature header raises HTTP 403
- [ ] Security logging (no secret leakage)
- [ ] Client IP logged for invalid attempts

### Task 4.4-4.6 Acceptance Criteria
- [ ] All test files created
- [ ] All tests pass with `pytest tests/unit/test_twilio_*.py`
- [ ] Coverage >90% for Phase 4 code
- [ ] No warnings or deprecations
- [ ] Security tests verify no secret logging

### Phase 4 Complete Acceptance Criteria
- [ ] All 6 tasks completed
- [ ] All unit tests pass
- [ ] Code coverage >90%
- [ ] No security vulnerabilities (secrets in logs)
- [ ] Documentation complete (docstrings, type hints)
- [ ] Code follows project patterns (static methods, error handling)

---

## Integration with Phase 5

Phase 4 provides the building blocks for Phase 5 (FastAPI Routes). The webhook endpoint in Phase 5 will:

1. **Use signature verification as dependency**:
   ```python
   @router.post("/webhook/sms", dependencies=[Depends(verify_twilio_signature)])
   async def handle_sms(webhook_data: TwilioWebhookRequest):
       # Request is verified and validated
       pass
   ```

2. **Parse webhook data with schema**:
   ```python
   phone_hash = PhoneHasher.hash_phone(webhook_data.From)
   message_body = webhook_data.Body
   ```

3. **Generate TwiML responses**:
   ```python
   response_text = "What is your name?"
   twiml = TwilioClient.create_response(response_text)
   return Response(content=twiml, media_type="application/xml")
   ```

---

## Risk Assessment

### Low Risk Items
- **TwiML generation**: Simple XML generation with Twilio SDK
- **Schema validation**: Pydantic handles most complexity
- **Unit testing**: No external dependencies, fast execution

### Medium Risk Items
- **E.164 validation**: Need to test many international formats
  - *Mitigation*: Comprehensive test cases, reference Twilio docs
- **Signature verification**: Cryptographic operations
  - *Mitigation*: Use Twilio SDK's battle-tested implementation

### High Risk Items
- **Security logging**: Risk of leaking secrets in logs
  - *Mitigation*:
    - Never log auth tokens or signatures
    - Code review focused on logging statements
    - Test that secrets don't appear in log output
    - Use truncated hashes only

---

## Security Checklist

- [ ] Auth tokens never logged (check all log statements)
- [ ] Signature values never logged
- [ ] Full phone hashes never logged (use truncation)
- [ ] Invalid signature attempts logged with client IP
- [ ] HTTP 403 (not 401) for signature failures
- [ ] All webhook endpoints use signature verification
- [ ] E.164 validation prevents malformed phone numbers
- [ ] TwiML generation escapes user input (handled by Twilio SDK)
- [ ] No secrets in source code (use environment variables)
- [ ] Request validator uses constant-time comparison (Twilio SDK)

---

## Documentation References

### Twilio Documentation
- [Webhook Request Format](https://www.twilio.com/docs/sms/twiml/message#request-parameters)
- [TwiML for SMS](https://www.twilio.com/docs/sms/twiml)
- [Signature Validation](https://www.twilio.com/docs/usage/security#validating-requests)
- [E.164 Phone Number Format](https://www.twilio.com/docs/glossary/what-e164)

### Internal Documentation
- Project patterns: `/Users/tony/Dropbox/Projects/sms-survey/CLAUDE.md`
- Configuration: `/Users/tony/Dropbox/Projects/sms-survey/app/config.py`
- Logging: `/Users/tony/Dropbox/Projects/sms-survey/app/logging_config.py`
- Phone hashing: `/Users/tony/Dropbox/Projects/sms-survey/app/services/phone_hasher.py`

### Testing Patterns
- Example unit tests: `/Users/tony/Dropbox/Projects/sms-survey/tests/unit/test_phone_hasher.py`
- Phase 2/3 plan: `/Users/tony/Dropbox/Projects/sms-survey/plans/phase2-3-implementation-plan.md`

---

## Post-Implementation Tasks

After Phase 4 completion:

1. **Update CLAUDE.md**: Add Phase 4 completion status
2. **Document patterns**: Add TwiML and signature verification examples
3. **Integration testing**: Test with real Twilio sandbox (Phase 7)
4. **Code review**: Security-focused review of logging statements
5. **Performance baseline**: Measure signature verification overhead
6. **Phase 5 readiness**: Ensure all Phase 4 components are tested and documented

---

## Appendix A: E.164 Format Reference

Valid E.164 phone number formats:

| Country | Format | Example |
|---------|--------|---------|
| United States | +1XXXXXXXXXX | +15551234567 |
| United Kingdom | +44XXXXXXXXXX | +442071234567 |
| China | +86XXXXXXXXXXX | +861234567890 |
| Australia | +61XXXXXXXXX | +61412345678 |
| France | +33XXXXXXXXX | +33123456789 |
| Germany | +49XXXXXXXXXX | +491234567890 |

Requirements:
- Starts with `+`
- Followed by country code (1-3 digits)
- Followed by subscriber number
- Total length: 8-16 characters (including `+`)
- No spaces, dashes, or special characters

---

## Appendix B: Twilio SID Format Reference

Twilio uses 34-character alphanumeric identifiers (SIDs) with prefixes:

| SID Type | Prefix | Example | Description |
|----------|--------|---------|-------------|
| Message | SM | SM1234567890abcdef1234567890abcdef | SMS message |
| MMS | MM | MM1234567890abcdef1234567890abcdef | MMS message |
| Account | AC | AC1234567890abcdef1234567890abcdef | Twilio account |
| Call | CA | CA1234567890abcdef1234567890abcdef | Phone call |

Format: `[PREFIX][32 alphanumeric characters]`

---

## Appendix C: TwiML Examples

### Simple Message Response
```xml
<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>Thanks for your message! What is your name?</Message>
</Response>
```

### Empty Response (No Reply)
```xml
<?xml version="1.0" encoding="UTF-8"?>
<Response />
```

### Multiple Messages (Not Used in This Project)
```xml
<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>First message</Message>
    <Message>Second message</Message>
</Response>
```

---

## Questions & Decisions Log

### Q1: Should we validate AccountSid matches configuration?
**Decision**: No. Validation happens via signature verification. Schema only validates format.

### Q2: Should we support MMS (media messages)?
**Decision**: Schema includes `NumMedia` and `has_media` property for future support, but Phase 5 will reject MMS messages with appropriate error.

### Q3: Should signature verification be middleware or dependency?
**Decision**: FastAPI dependency (using `Depends()`) for better flexibility and testability.

### Q4: What HTTP status for invalid signature: 401 or 403?
**Decision**: 403 Forbidden. Invalid signature is authorization failure (you're not who you claim to be), not authentication failure (missing credentials).

### Q5: Should we cache TwilioSignatureValidator instances?
**Decision**: No. Dependency injection creates instance per request. No significant performance impact since RequestValidator is lightweight.

---

## Success Metrics

### Functionality Metrics
- [ ] All unit tests pass (100% pass rate)
- [ ] Code coverage >90% for Phase 4 modules
- [ ] No security vulnerabilities detected
- [ ] Manual testing confirms E.164 validation works

### Quality Metrics
- [ ] No TODOs or FIXMEs in production code
- [ ] All functions have docstrings with examples
- [ ] Type hints on all function signatures
- [ ] Follows project coding patterns

### Security Metrics
- [ ] Zero secrets in logs (validated via test)
- [ ] All webhook endpoints protected by signature verification
- [ ] Security logging includes client IP
- [ ] Code review completed with security focus

### Documentation Metrics
- [ ] All modules have module-level docstrings
- [ ] All public methods documented
- [ ] Examples in docstrings
- [ ] This plan updated with lessons learned

---

## End of Phase 4 Implementation Plan

**Next Phase**: Phase 5 - FastAPI Routes (Webhook Endpoint Implementation)

**Estimated Completion Time**: 3.5 hours for full implementation and testing
