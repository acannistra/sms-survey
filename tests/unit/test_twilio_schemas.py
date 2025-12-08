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
