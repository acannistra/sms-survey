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
