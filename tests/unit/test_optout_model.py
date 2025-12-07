"""Unit tests for OptOut model class methods.

These tests verify the behavior of OptOut class methods for managing
opt-out records in the database.
"""

from datetime import datetime, timezone

import pytest

from app.models.optout import OptOut


class TestOptOutClassMethods:
    """Test OptOut class methods."""

    def test_is_opted_out_false_when_not_exists(self, db_session, sample_phone_hash):
        """Test is_opted_out returns False when phone hash not in table."""
        # Check a phone hash that doesn't exist
        result = OptOut.is_opted_out(db_session, sample_phone_hash)
        assert result is False

    def test_is_opted_out_true_when_exists(self, db_session, sample_phone_hash):
        """Test is_opted_out returns True when phone hash exists."""
        # Add opt-out record
        optout = OptOut(
            phone_hash=sample_phone_hash,
            opted_out_at=datetime.now(timezone.utc),
        )
        db_session.add(optout)
        db_session.commit()

        # Check should return True
        result = OptOut.is_opted_out(db_session, sample_phone_hash)
        assert result is True

    def test_add_optout_creates_new_record(self, db_session, sample_phone_hash):
        """Test add_optout creates a new opt-out record."""
        # Should not be opted out initially
        assert OptOut.is_opted_out(db_session, sample_phone_hash) is False

        # Add opt-out
        optout = OptOut.add_optout(db_session, sample_phone_hash, "STOP")
        db_session.commit()

        # Should now be opted out
        assert OptOut.is_opted_out(db_session, sample_phone_hash) is True
        assert optout.phone_hash == sample_phone_hash
        assert optout.opt_out_message == "STOP"
        assert optout.opted_out_at is not None

    def test_add_optout_updates_existing_record(self, db_session, sample_phone_hash):
        """Test add_optout updates existing record instead of creating duplicate."""
        # Create initial opt-out
        first_optout = OptOut.add_optout(db_session, sample_phone_hash, "STOP")
        db_session.commit()
        first_timestamp = first_optout.opted_out_at

        # Try to add again with different message
        second_optout = OptOut.add_optout(db_session, sample_phone_hash, "UNSUBSCRIBE")
        db_session.commit()

        # Should be the same record (updated, not created)
        assert second_optout.phone_hash == sample_phone_hash
        assert second_optout.opt_out_message == "UNSUBSCRIBE"
        assert second_optout.opted_out_at >= first_timestamp

        # Should only have one record in database
        all_optouts = db_session.query(OptOut).filter(
            OptOut.phone_hash == sample_phone_hash
        ).all()
        assert len(all_optouts) == 1

    def test_add_optout_without_message(self, db_session, sample_phone_hash):
        """Test add_optout works without an opt-out message."""
        optout = OptOut.add_optout(db_session, sample_phone_hash)
        db_session.commit()

        assert optout.phone_hash == sample_phone_hash
        assert optout.opt_out_message is None
        assert OptOut.is_opted_out(db_session, sample_phone_hash) is True

    def test_remove_optout_deletes_record(self, db_session, sample_phone_hash):
        """Test remove_optout deletes the opt-out record."""
        # Add opt-out
        OptOut.add_optout(db_session, sample_phone_hash, "STOP")
        db_session.commit()
        assert OptOut.is_opted_out(db_session, sample_phone_hash) is True

        # Remove opt-out
        result = OptOut.remove_optout(db_session, sample_phone_hash)
        db_session.commit()

        # Should return True and remove the record
        assert result is True
        assert OptOut.is_opted_out(db_session, sample_phone_hash) is False

    def test_remove_optout_returns_false_when_not_found(
        self, db_session, sample_phone_hash
    ):
        """Test remove_optout returns False when phone hash not found."""
        # Try to remove opt-out that doesn't exist
        result = OptOut.remove_optout(db_session, sample_phone_hash)

        # Should return False
        assert result is False

    def test_repr(self, db_session, sample_phone_hash):
        """Test string representation."""
        optout = OptOut(
            phone_hash=sample_phone_hash,
            opted_out_at=datetime.now(timezone.utc),
            opt_out_message="STOP",
        )
        db_session.add(optout)
        db_session.commit()

        repr_str = repr(optout)

        # Should include key information
        assert "OptOut" in repr_str
        assert "opted_out_at" in repr_str

        # Should truncate phone_hash for privacy
        assert sample_phone_hash[:12] in repr_str
        assert sample_phone_hash not in repr_str  # Full hash not shown
