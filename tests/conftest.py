"""Pytest configuration and shared fixtures.

This module provides fixtures and configuration used across all tests.
"""

import os
from typing import Generator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

# Set required environment variables for tests BEFORE importing app modules
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("TWILIO_ACCOUNT_SID", "test_account_sid")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test_auth_token")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "+15551234567")
os.environ.setdefault("SECRET_KEY", "test_secret_key_for_testing_only")
os.environ.setdefault("PHONE_HASH_SALT", "test_salt_for_hashing_phones")
os.environ.setdefault("ENVIRONMENT", "development")

from app.models.database import Base


@pytest.fixture(scope="function")
def db_engine():
    """Create a test database engine with SQLite in-memory database.

    Yields:
        Engine: SQLAlchemy engine for testing

    Note:
        Uses SQLite in-memory database for fast, isolated tests.
        Database is created fresh for each test function.
    """
    # Create in-memory SQLite database
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,  # Set to True for SQL debugging
    )

    # Enable foreign key support for SQLite
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Create all tables
    Base.metadata.create_all(engine)

    yield engine

    # Drop all tables after test
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine) -> Generator[Session, None, None]:
    """Create a test database session.

    Args:
        db_engine: Test database engine fixture

    Yields:
        Session: SQLAlchemy session for testing

    Note:
        Session is rolled back after each test to ensure isolation.
    """
    # Create session factory
    TestSessionLocal = sessionmaker(
        bind=db_engine,
        autocommit=False,
        autoflush=False,
    )

    # Create session
    session = TestSessionLocal()

    yield session

    # Rollback any uncommitted changes
    session.rollback()
    session.close()


@pytest.fixture
def sample_phone_hash() -> str:
    """Provide a sample phone hash for testing.

    Returns:
        str: 64-character hex string (SHA-256 hash)
    """
    return "a1b2c3d4e5f6" + "0" * 52  # 64 chars total


@pytest.fixture
def sample_survey_id() -> str:
    """Provide a sample survey ID for testing.

    Returns:
        str: Survey identifier
    """
    return "test_survey"


@pytest.fixture
def sample_survey_version() -> str:
    """Provide a sample survey version for testing.

    Returns:
        str: Git commit SHA
    """
    return "abc123def456"
