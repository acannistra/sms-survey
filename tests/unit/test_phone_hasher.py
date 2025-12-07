"""Unit tests for phone number hashing service."""

import pytest
from app.services.phone_hasher import PhoneHasher


class TestPhoneHasher:
    """Test suite for PhoneHasher class."""

    def test_deterministic_hashing(self):
        """Test that same input produces same hash."""
        phone = "+15551234567"
        hash1 = PhoneHasher.hash_phone(phone)
        hash2 = PhoneHasher.hash_phone(phone)

        assert hash1 == hash2, "Same phone number should produce identical hashes"

    def test_hash_format(self):
        """Test that hash is 64-character hex string."""
        phone = "+15551234567"
        phone_hash = PhoneHasher.hash_phone(phone)

        # SHA-256 produces 64-character hex string
        assert len(phone_hash) == 64, "Hash should be 64 characters (SHA-256 hex)"

        # All characters should be valid hex
        assert all(c in '0123456789abcdef' for c in phone_hash), \
            "Hash should contain only hex characters (0-9, a-f)"

    def test_different_phones_produce_different_hashes(self):
        """Test that different phone numbers produce different hashes."""
        phone1 = "+15551234567"
        phone2 = "+15559876543"

        hash1 = PhoneHasher.hash_phone(phone1)
        hash2 = PhoneHasher.hash_phone(phone2)

        assert hash1 != hash2, "Different phone numbers should produce different hashes"

    def test_normalization_strips_whitespace(self):
        """Test that normalization removes leading and trailing whitespace."""
        phone_with_whitespace = "  +15551234567  "
        phone_clean = "+15551234567"

        normalized = PhoneHasher.normalize_e164(phone_with_whitespace)
        assert normalized == phone_clean, "Normalization should strip whitespace"

    def test_normalization_affects_hash(self):
        """Test that whitespace is normalized before hashing."""
        phone_with_whitespace = "  +15551234567  "
        phone_clean = "+15551234567"

        hash1 = PhoneHasher.hash_phone(phone_with_whitespace)
        hash2 = PhoneHasher.hash_phone(phone_clean)

        assert hash1 == hash2, "Hashes should be identical after normalization"

    def test_truncation_format(self):
        """Test that truncation produces correct format (12 chars + '...')."""
        phone = "+15551234567"
        phone_hash = PhoneHasher.hash_phone(phone)

        truncated = PhoneHasher.truncate_for_logging(phone_hash)

        # Should be 12 chars + "..." = 15 total characters
        assert len(truncated) == 15, "Truncated hash should be 15 characters (12 + '...')"
        assert truncated.endswith("..."), "Truncated hash should end with '...'"
        assert truncated[:12] == phone_hash[:12], \
            "Truncated hash should start with first 12 characters of full hash"

    def test_truncation_preserves_prefix(self):
        """Test that truncation preserves the first 12 characters."""
        phone = "+15551234567"
        phone_hash = PhoneHasher.hash_phone(phone)
        truncated = PhoneHasher.truncate_for_logging(phone_hash)

        # First 12 chars should match
        assert truncated[:12] == phone_hash[:12], \
            "Truncation should preserve first 12 characters"
