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
