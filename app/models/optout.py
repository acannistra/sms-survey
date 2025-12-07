"""OptOut model for managing SMS opt-out requests.

This module defines the OptOut model which tracks users who have opted out
of receiving SMS messages via STOP, UNSUBSCRIBE, or similar keywords.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    String,
    DateTime,
    text,
    select,
)
from sqlalchemy.orm import Mapped, mapped_column, Session

from app.models.database import Base


class OptOut(Base):
    """Model for tracking SMS opt-out requests.

    When a user texts STOP, UNSUBSCRIBE, CANCEL, END, or QUIT, their
    phone hash is added to this table. The system must check this table
    before sending any SMS messages to ensure compliance with SMS regulations.

    Attributes:
        phone_hash: SHA-256 hash of phone number (primary key)
        opted_out_at: When the user opted out
        opt_out_message: The message they sent (e.g., "STOP", "UNSUBSCRIBE")
    """

    __tablename__ = "optouts"

    # Phone Hash (primary key, unique)
    phone_hash: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        comment="SHA-256 hash of phone number for privacy"
    )

    # Opt-out Metadata
    opted_out_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="When the user opted out"
    )
    opt_out_message: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        comment="The opt-out message sent by user (e.g., STOP)"
    )

    @classmethod
    def is_opted_out(cls, db: Session, phone_hash: str) -> bool:
        """Check if a phone hash has opted out.

        Args:
            db: Database session
            phone_hash: SHA-256 hash of phone number to check

        Returns:
            bool: True if opted out, False otherwise

        Example:
            if OptOut.is_opted_out(db, phone_hash):
                return "You have opted out. Text START to opt back in."
        """
        result = db.execute(
            select(cls).where(cls.phone_hash == phone_hash)
        ).first()
        return result is not None

    @classmethod
    def add_optout(
        cls,
        db: Session,
        phone_hash: str,
        opt_out_message: Optional[str] = None
    ) -> "OptOut":
        """Add a phone hash to the opt-out list.

        Args:
            db: Database session
            phone_hash: SHA-256 hash of phone number to opt out
            opt_out_message: Optional message sent by user (e.g., "STOP")

        Returns:
            OptOut: The created opt-out record

        Note:
            If the phone hash is already opted out, this method updates
            the opt-out timestamp and message rather than raising an error.

        Example:
            optout = OptOut.add_optout(db, phone_hash, "STOP")
            db.commit()
        """
        # Check if already opted out
        existing = db.execute(
            select(cls).where(cls.phone_hash == phone_hash)
        ).scalar_one_or_none()

        if existing:
            # Update existing opt-out record
            existing.opted_out_at = datetime.now(timezone.utc)
            existing.opt_out_message = opt_out_message
            return existing
        else:
            # Create new opt-out record
            optout = cls(
                phone_hash=phone_hash,
                opted_out_at=datetime.now(timezone.utc),
                opt_out_message=opt_out_message,
            )
            db.add(optout)
            return optout

    @classmethod
    def remove_optout(cls, db: Session, phone_hash: str) -> bool:
        """Remove a phone hash from the opt-out list (opt back in).

        Args:
            db: Database session
            phone_hash: SHA-256 hash of phone number to opt back in

        Returns:
            bool: True if opt-out was removed, False if not found

        Example:
            if OptOut.remove_optout(db, phone_hash):
                db.commit()
                return "You have opted back in to SMS notifications."
        """
        optout = db.execute(
            select(cls).where(cls.phone_hash == phone_hash)
        ).scalar_one_or_none()

        if optout:
            db.delete(optout)
            return True
        return False

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"<OptOut(phone_hash={self.phone_hash[:12]}..., "
            f"opted_out_at={self.opted_out_at})>"
        )
