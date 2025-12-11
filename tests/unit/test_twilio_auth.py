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
