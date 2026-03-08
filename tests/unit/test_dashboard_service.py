"""Unit tests for dashboard_service.py.

Tests are isolated using SQLite in-memory databases via the conftest fixtures.
"""

import os
from datetime import datetime, timezone

import pytest

# Env vars must be set before importing app modules (conftest does this, but be safe)
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("TWILIO_ACCOUNT_SID", "test_account_sid")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test_auth_token")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "+15551234567")
os.environ.setdefault("SECRET_KEY", "test_secret_key_for_testing_only")
os.environ.setdefault("PHONE_HASH_SALT", "test_salt_for_hashing_phones")
os.environ.setdefault("ENVIRONMENT", "development")

from app.models.session import SurveySession
from app.models.optout import OptOut
from app.services.dashboard_service import (
    get_survey_list,
    get_survey_stats,
    get_survey_funnel,
    get_export_data,
    generate_xlsx,
)
from app.services.survey_loader import SurveyLoader, SurveyNotFoundError


# ---------------------------------------------------------------------------
# Shared valid survey YAML template (values quoted to avoid YAML bool coercion)
# ---------------------------------------------------------------------------

def _make_survey_yaml(survey_id: str, name: str, start_word: str) -> str:
    return f"""
metadata:
  id: {survey_id}
  name: "{name}"
  description: "A test survey"
  version: "1.0.0"
  start_words:
    - "{start_word}"

consent:
  step_id: consent
  text: "Reply YES or NO."
  accept_values:
    - "yes"
  decline_values:
    - "no"
  decline_message: "OK, goodbye."

steps:
  - id: consent
    text: "Reply YES or NO."
    type: choice
    validation:
      choices:
        - display: "Yes"
          value: "true"
        - display: "No"
          value: "false"
    store_as: consent_given
    next: done

  - id: done
    text: "Thanks!"
    type: terminal
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session(
    phone_hash: str = "a" * 64,
    survey_id: str = "test_survey",
    consent_given: bool = True,
    completed: bool = False,
) -> SurveySession:
    """Build a SurveySession ORM object (not yet added to DB)."""
    s = SurveySession(
        phone_hash=phone_hash,
        survey_id=survey_id,
        survey_version="abc123",
        current_step="ask_name",
        consent_given=consent_given,
        started_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc) if completed else None,
        retry_count=0,
        context={},
    )
    return s


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_get_survey_list_returns_surveys(tmp_path):
    """get_survey_list() should return at least one survey when YAMLs exist."""
    import app.services.survey_loader as loader_mod

    survey_dir = tmp_path / "surveys"
    survey_dir.mkdir()
    (survey_dir / "test_survey.yaml").write_text(
        _make_survey_yaml("test_survey", "Test Survey", "test")
    )

    original_loader = loader_mod._loader_instance
    loader_mod._loader_instance = SurveyLoader(surveys_dir=str(survey_dir))
    try:
        result = get_survey_list()
        assert len(result.surveys) == 1
        assert result.surveys[0].survey_id == "test_survey"
        assert result.surveys[0].name == "Test Survey"
    finally:
        loader_mod._loader_instance = original_loader


def test_get_survey_stats_empty_db(db_session, tmp_path):
    """get_survey_stats() should return all zeros when no sessions exist."""
    import app.services.survey_loader as loader_mod

    survey_dir = tmp_path / "surveys"
    survey_dir.mkdir()
    (survey_dir / "empty_survey.yaml").write_text(
        _make_survey_yaml("empty_survey", "Empty Survey", "go")
    )

    original_loader = loader_mod._loader_instance
    loader_mod._loader_instance = SurveyLoader(surveys_dir=str(survey_dir))
    try:
        result = get_survey_stats(db_session, "empty_survey")
        assert result.sessions_started == 0
        assert result.consents_given == 0
        assert result.sessions_completed == 0
        assert result.unique_participants == 0
        assert result.active_last_48h == 0
        assert result.opt_outs == 0
        assert result.avg_completion_pct == 0.0
    finally:
        loader_mod._loader_instance = original_loader


def test_get_survey_stats_with_sessions(db_session, tmp_path):
    """get_survey_stats() should reflect inserted sessions correctly."""
    import app.services.survey_loader as loader_mod

    survey_dir = tmp_path / "surveys"
    survey_dir.mkdir()
    (survey_dir / "alpha_survey.yaml").write_text(
        _make_survey_yaml("alpha_survey", "Alpha Survey", "alpha")
    )

    original_loader = loader_mod._loader_instance
    loader_mod._loader_instance = SurveyLoader(surveys_dir=str(survey_dir))
    try:
        # Insert 2 sessions: 1 completed with consent, 1 not completed with consent
        s1 = _make_session(
            phone_hash="a" * 64, survey_id="alpha_survey", consent_given=True, completed=True
        )
        s2 = _make_session(
            phone_hash="b" * 64, survey_id="alpha_survey", consent_given=True, completed=False
        )
        db_session.add_all([s1, s2])
        db_session.commit()

        result = get_survey_stats(db_session, "alpha_survey")
        assert result.sessions_started == 2
        assert result.consents_given == 2
        assert result.sessions_completed == 1
        assert result.unique_participants == 2
        assert result.avg_completion_pct == 50.0
    finally:
        loader_mod._loader_instance = original_loader


def test_get_export_data_phone_hash_truncated(db_session, tmp_path):
    """phone_hash_prefix must be exactly 12 characters — never the full hash."""
    import app.services.survey_loader as loader_mod

    survey_dir = tmp_path / "surveys"
    survey_dir.mkdir()
    (survey_dir / "priv_survey.yaml").write_text(
        _make_survey_yaml("priv_survey", "Privacy Survey", "priv")
    )

    original_loader = loader_mod._loader_instance
    loader_mod._loader_instance = SurveyLoader(surveys_dir=str(survey_dir))
    try:
        full_hash = "c" * 64
        s = _make_session(phone_hash=full_hash, survey_id="priv_survey")
        db_session.add(s)
        db_session.commit()

        rows = get_export_data(db_session, "priv_survey")
        assert len(rows) == 1
        assert rows[0].phone_hash_prefix == "c" * 12
        assert len(rows[0].phone_hash_prefix) == 12
        # Ensure the full hash is not present anywhere in the result
        assert rows[0].phone_hash_prefix != full_hash
    finally:
        loader_mod._loader_instance = original_loader


def test_generate_xlsx_returns_bytes():
    """generate_xlsx() should return bytes starting with PK (XLSX magic bytes)."""
    from app.schemas.dashboard import ExportRow

    rows = [
        ExportRow(
            session_id=1,
            phone_hash_prefix="abcdef012345",
            survey_id="test",
            started_at=datetime.now(timezone.utc),
            completed_at=None,
            consent_given=True,
            context={"name": "Alice"},
        )
    ]
    result = generate_xlsx(rows)
    assert isinstance(result, bytes)
    assert len(result) > 0
    # XLSX files are ZIP archives — they start with PK (0x50 0x4B)
    assert result[:2] == b"PK"
