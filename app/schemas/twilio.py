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
