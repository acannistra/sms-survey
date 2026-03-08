"""Unit tests for dashboard API routes.

Uses the shared `test_client` fixture from conftest.py which wires up
a temporary SQLite database and overrides the DB dependency.
"""

import os

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("TWILIO_ACCOUNT_SID", "test_account_sid")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test_auth_token")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "+15551234567")
os.environ.setdefault("SECRET_KEY", "test_secret_key_for_testing_only")
os.environ.setdefault("PHONE_HASH_SALT", "test_salt_for_hashing_phones")
os.environ.setdefault("ENVIRONMENT", "development")

from app.services.survey_loader import SurveyLoader
import app.services.survey_loader as loader_mod


SURVEY_YAML = """
metadata:
  id: snoq_survey
  name: "Snoqualmie Survey"
  description: "A test survey for dashboard routes"
  version: "1.0.0"
  start_words:
    - "snoq"
    - "gohere"

consent:
  step_id: consent
  text: "Reply YES to continue or NO to opt out."
  accept_values:
    - "yes"
    - "y"
  decline_values:
    - "no"
    - "n"
  decline_message: "Thanks anyway!"

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
    text: "What is your name?"
    type: text
    validation:
      min_length: 2
      max_length: 50
    store_as: name
    next: done

  - id: done
    text: "Thanks!"
    type: terminal
"""


@pytest.fixture(autouse=True)
def patch_survey_loader(tmp_path):
    """Inject a test SurveyLoader pointing at a temporary surveys directory."""
    survey_dir = tmp_path / "surveys"
    survey_dir.mkdir()
    (survey_dir / "snoq_survey.yaml").write_text(SURVEY_YAML)

    original = loader_mod._loader_instance
    loader_mod._loader_instance = SurveyLoader(surveys_dir=str(survey_dir))
    yield
    loader_mod._loader_instance = original


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_list_surveys_endpoint(test_client):
    """GET /api/dashboard/surveys should return 200 with a surveys list."""
    resp = test_client.get("/api/dashboard/surveys")
    assert resp.status_code == 200
    body = resp.json()
    assert "surveys" in body
    assert isinstance(body["surveys"], list)
    assert any(s["survey_id"] == "snoq_survey" for s in body["surveys"])


def test_stats_endpoint_unknown_survey(test_client):
    """GET /api/dashboard/surveys/{id}/stats should return 404 for unknown survey."""
    resp = test_client.get("/api/dashboard/surveys/nonexistent_survey_xyz/stats")
    assert resp.status_code == 404


def test_stats_endpoint_known_survey(test_client):
    """GET /api/dashboard/surveys/{id}/stats should return 200 with sessions_started."""
    resp = test_client.get("/api/dashboard/surveys/snoq_survey/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert "sessions_started" in body
    assert body["survey_id"] == "snoq_survey"


def test_funnel_endpoint(test_client):
    """GET /api/dashboard/surveys/{id}/funnel should return 200 with a funnel list."""
    resp = test_client.get("/api/dashboard/surveys/snoq_survey/funnel")
    assert resp.status_code == 200
    body = resp.json()
    assert "funnel" in body
    assert isinstance(body["funnel"], list)


def test_export_csv(test_client):
    """Export as CSV should return 200 and Content-Disposition with .csv."""
    resp = test_client.get("/api/dashboard/surveys/snoq_survey/export?format=csv")
    assert resp.status_code == 200
    content_disposition = resp.headers.get("content-disposition", "")
    assert ".csv" in content_disposition


def test_export_json(test_client):
    """Export as JSON should return 200 and Content-Disposition with .json."""
    resp = test_client.get("/api/dashboard/surveys/snoq_survey/export?format=json")
    assert resp.status_code == 200
    content_disposition = resp.headers.get("content-disposition", "")
    assert ".json" in content_disposition


def test_export_xlsx(test_client):
    """Export as XLSX should return 200 with openxmlformats content type."""
    resp = test_client.get("/api/dashboard/surveys/snoq_survey/export?format=xlsx")
    assert resp.status_code == 200
    assert "openxmlformats" in resp.headers.get("content-type", "")


def test_export_invalid_format(test_client):
    """Export with unsupported format should return 422 Unprocessable Entity."""
    resp = test_client.get("/api/dashboard/surveys/snoq_survey/export?format=xml")
    assert resp.status_code == 422
