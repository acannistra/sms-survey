"""Phone number hashing service for privacy protection.

This module provides one-way hashing of phone numbers using SHA-256 with
application salt, enabling the privacy claim: "We don't store your phone number".

The hashing is deterministic, allowing session lookups and opt-out tracking
without storing plaintext phone numbers.
"""

import hashlib
from app.config import get_settings


class PhoneHasher:
    """
    One-way hashing service for phone number privacy.

    Phone numbers are hashed with SHA-256 + application salt, allowing us to:
    - Lookup existing sessions (deterministic hash)
    - Honor opt-out requests
    - Never store plaintext phone numbers

    Security notes:
    - Salt must be kept secret and never committed to git
    - Changing salt will orphan existing sessions
    - Twilio webhooks still receive plaintext (we hash immediately)
    - Limited keyspace means hashes could theoretically be brute-forced,
      but strong salt makes this impractical

    Usage example:
        from app.services.phone_hasher import PhoneHasher

        # In webhook handler:
        phone_hash = PhoneHasher.hash_phone(request.From)

        # For logging:
        logger.info(f"Processing message from {PhoneHasher.truncate_for_logging(phone_hash)}")
    """

    @staticmethod
    def normalize_e164(phone: str) -> str:
        """
        Normalize phone number to E.164 format.

        Twilio sends numbers in E.164, so this mainly strips whitespace.

        Args:
            phone: Phone number string, potentially with whitespace

        Returns:
            Normalized phone number with whitespace removed

        Example:
            >>> PhoneHasher.normalize_e164(" +15551234567 ")
            '+15551234567'
        """
        return phone.strip()

    @staticmethod
    def hash_phone(phone: str) -> str:
        """
        One-way hash of phone number with application salt.

        Creates a deterministic SHA-256 hash that allows lookups without
        storing plaintext. The same phone number will always produce the
        same hash (given the same salt).

        Args:
            phone: Phone number in E.164 format (e.g., +15551234567)

        Returns:
            64-character hex string (SHA-256 hash)

        Example:
            >>> hash1 = PhoneHasher.hash_phone("+15551234567")
            >>> hash2 = PhoneHasher.hash_phone("+15551234567")
            >>> hash1 == hash2
            True
            >>> len(hash1)
            64
        """
        settings = get_settings()
        normalized = PhoneHasher.normalize_e164(phone)

        # Combine phone with secret salt
        salted = f"{normalized}:{settings.phone_hash_salt}"

        # SHA-256 hash
        hash_bytes = hashlib.sha256(salted.encode('utf-8')).digest()
        return hash_bytes.hex()

    @staticmethod
    def truncate_for_logging(phone_hash: str) -> str:
        """
        Truncate hash for safe logging (first 12 chars).

        Full hashes should not appear in logs to prevent correlation attacks.
        This provides enough information for debugging while maintaining privacy.

        Args:
            phone_hash: 64-character hash from hash_phone()

        Returns:
            First 12 characters followed by "..."

        Example:
            >>> full_hash = "a1b2c3d4e5f6" + "0" * 52
            >>> PhoneHasher.truncate_for_logging(full_hash)
            'a1b2c3d4e5f6...'
        """
        return f"{phone_hash[:12]}..."


# Usage in webhook:
# from app.services.phone_hasher import PhoneHasher
# phone_hash = PhoneHasher.hash_phone(request.From)
