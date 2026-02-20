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
# Import all models to ensure tables are registered
from app.models.session import SurveySession
from app.models.response import SurveyResponse
from app.models.optout import OptOut


@pytest.fixture(scope="function")
def db_engine():
    """Create a test database engine with SQLite in-memory database.

    Yields:
        Engine: SQLAlchemy engine for testing

    Note:
        Uses SQLite in-memory database for fast, isolated tests.
        Database is created fresh for each test function.
    """
    # Create in-memory SQLite database with check_same_thread=False for TestClient
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,  # Set to True for SQL debugging
        connect_args={"check_same_thread": False},
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


@pytest.fixture
def test_client(tmp_path):
    """Create FastAPI TestClient with database override.

    Yields:
        TestClient: FastAPI test client for API testing

    Note:
        Uses a temporary file-based SQLite database to avoid in-memory
        connection issues with TestClient's background tasks.
    """
    import tempfile
    from pathlib import Path
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.main import app
    from app.models import database as db_module

    # Create temporary database file
    db_file = tmp_path / "test.db"
    test_db_url = f"sqlite:///{db_file}"

    # Create test engine
    test_engine = create_engine(
        test_db_url,
        echo=False,
        connect_args={"check_same_thread": False},
    )

    # Create all tables
    Base.metadata.create_all(test_engine)

    # Replace the module-level engine with our test engine
    original_engine = db_module.engine
    original_session_local = db_module.SessionLocal

    db_module.engine = test_engine
    db_module.SessionLocal = sessionmaker(
        bind=test_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )

    # Create test client
    client = TestClient(app)
    yield client

    # Cleanup
    client.close()
    db_module.engine = original_engine
    db_module.SessionLocal = original_session_local
    app.dependency_overrides.clear()
    test_engine.dispose()


@pytest.fixture
def test_phone_number() -> str:
    """Provide a test phone number in E.164 format.

    Returns:
        str: Test phone number
    """
    return "+15551234567"


@pytest.fixture
def test_phone_hash(test_phone_number) -> str:
    """Provide a hashed test phone number.

    Args:
        test_phone_number: Test phone number fixture

    Returns:
        str: 64-character hex hash of test phone number
    """
    from app.services.phone_hasher import PhoneHasher
    return PhoneHasher.hash_phone(test_phone_number)


@pytest.fixture
def test_survey_fixture_path(tmp_path):
    """Create a temporary test survey YAML file.

    Args:
        tmp_path: Pytest temporary directory fixture

    Returns:
        Path: Path to test survey YAML file

    Note:
        Creates a minimal valid survey for testing.
    """
    survey_content = """
metadata:
  id: test_survey
  name: Test Survey
  description: A test survey
  version: 1.0.0
  start_words:
    - test
    - start

consent:
  step_id: consent
  text: "Reply YES to continue or NO to opt out."
  accept_values:
    - 'yes'
    - 'y'
  decline_values:
    - 'no'
    - 'n'
  decline_message: "Thanks anyway!"

settings:
  max_retry_attempts: 3
  retry_exceeded_message: "Too many attempts."
  timeout_hours: 24

steps:
  - id: consent
    text: "Reply YES to continue or NO to opt out."
    type: choice
    validation:
      choices:
        - display: "Yes"
          value: "true"
        - display: "No"
          value: "false"
    store_as: consent_given
    next: ask_name

  - id: ask_name
    text: "What's your name?"
    type: text
    validation:
      min_length: 2
      max_length: 50
    store_as: name
    error_message: "Please enter a valid name."
    next: completion

  - id: completion
    text: "Thanks {{ name }}!"
    type: terminal
"""

    survey_dir = tmp_path / "surveys"
    survey_dir.mkdir()
    survey_file = survey_dir / "test_survey.yaml"
    survey_file.write_text(survey_content)

    return survey_file
