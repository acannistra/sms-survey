# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an SMS survey engine that processes incoming text messages via Twilio webhooks, maintains survey state in PostgreSQL, and loads survey definitions from git-versioned YAML files. The system is serverless/stateless and designed for cost-efficient deployment on Fly.io.

**Current Status:** Phase 0 (Project Setup) complete. Database layer, survey engine, and API implementation pending.

## Core Architecture

### Privacy-First Design: Phone Number Hashing

**CRITICAL:** This system uses one-way SHA-256 hashing for all phone numbers to enable the privacy commitment "We don't store your phone number."

- Phone numbers are hashed **immediately** upon receipt from Twilio webhooks
- Database stores only 64-character hex hashes (never plaintext)
- `PHONE_HASH_SALT` environment variable is required and must be kept secret
- Logs must truncate hashes to first 12 characters (use `PhoneHasher.truncate_for_logging()`)
- Changing the salt orphans existing sessions (cannot look them up)

**Implementation locations:**
- Hashing service: `app/services/phone_hasher.py` (to be implemented in Phase 0, Task 0.6)
- Database models: `phone_hash` column (VARCHAR(64)) in `survey_sessions` and `optouts` tables
- Webhook handler: Hash incoming `From` field before any database operations

### Three-Layer Architecture

1. **Data Layer** (`app/models/`): SQLAlchemy ORM models with pessimistic locking (`SELECT FOR UPDATE`)
2. **Service Layer** (`app/services/`): Business logic isolated from HTTP/database concerns
3. **API Layer** (`app/routes/`): FastAPI endpoints with Twilio webhook signature verification

### Survey as Data Pattern

Surveys are defined in YAML files (`surveys/*.yaml`), not code. This allows non-technical staff to create and modify surveys without deployments.

**Key components:**
- **Survey Loader** (`app/services/survey_loader.py`): Loads and validates YAML with Pydantic schemas
- **Survey Engine** (`app/services/survey_engine.py`): State machine that processes user input, validates responses, and determines next steps
- **Template Renderer**: Jinja2 templating for dynamic question text (e.g., "Thanks {{ name }}! What's your zip code?")

**Survey flow:**
1. User texts Twilio number
2. Webhook hashes phone, looks up session (with row-level lock)
3. Engine validates input against current step's rules (regex/choice/text)
4. Updates context (e.g., `store_as: "name"` adds to Jinja2 context)
5. Evaluates conditional branching if present
6. Advances to next step, renders question text with context
7. Returns TwiML response to Twilio

## Development Commands

### Setup
```bash
# Activate virtual environment
source .venv/bin/activate

# Install dependencies (production + dev)
uv pip install -e ".[dev]"

# Configure environment
cp .env.example .env
# Edit .env with actual credentials (especially PHONE_HASH_SALT)
```

### Testing
```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/unit/test_survey_engine.py

# Verbose output
pytest -v

# Verify Phase 0 setup
python test_phase0.py
```

### Database Migrations (Phase 1+)
```bash
# Create new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Show current migration
alembic current
```

### Running the App (Phase 5+)
```bash
# Development server with auto-reload
uvicorn app.main:app --reload

# Production
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Implementation Phases

The project is built in 9 sequential phases (see `plans/implementation-plan.md` for complete details):

0. **Project Setup** (COMPLETE) - Poetry/uv, config, logging, phone hasher
1. **Database Layer** - SQLAlchemy models, Alembic migrations, pessimistic locking
2. **Survey Loading** - YAML schemas, Pydantic validation, survey loader service
3. **Survey Engine** - State machine, Jinja2 rendering, branching logic
4. **Twilio Integration** - Webhook schemas, TwiML generation, signature verification
5. **FastAPI Routes** - Webhook endpoint, session management, opt-out handling
6. **Deployment** - Dockerfile, Fly.io config, release commands
7. **Testing** - Unit, integration, E2E tests (>80% coverage target)
8. **Documentation** - README, survey format docs, code comments
9. **Production Readiness** - Monitoring, rate limiting, security hardening

**Critical path dependencies:**
- Phase 0 → Phase 1 (database needs config)
- Phase 2 → Phase 3 (engine needs survey loader)
- Phases 1, 3, 4 → Phase 5 (routes need database, engine, and Twilio)

## Key Files & Patterns

### Configuration (`app/config.py`)
- Pydantic Settings with environment variable validation
- Use `get_settings()` (cached) to access config throughout the app
- Required env vars: `DATABASE_URL`, `TWILIO_*`, `SECRET_KEY`, `PHONE_HASH_SALT`
- Validators ensure phone numbers are E.164 format, log levels are valid

### Logging (`app/logging_config.py`)
- JSON formatter for production, colored formatter for development
- Context fields: `phone_hash`, `survey_id`, `session_id`
- Use `get_logger(__name__)` to get logger with context support
- **Never log plaintext phone numbers or full hashes**

### Survey YAML Format (`surveys/README.md`)
See surveys/README.md for full documentation. Key points:
- Four question types: `text`, `regex`, `choice`, `terminal`
- Conditional branching with `next_conditional` (Python expressions)
- Jinja2 variables: `{{ variable_name }}` references stored values
- Validation rules: patterns, choices, length constraints
- Settings: `max_retry_attempts`, `timeout_hours`

### Database Patterns
**Pessimistic Locking for Race Condition Prevention:**
```python
session = db.query(SurveySession).filter(
    SurveySession.phone_hash == phone_hash,
    SurveySession.survey_id == survey_id,
    SurveySession.completed_at == None
).with_for_update().first()
```

**Important:** Always query by `phone_hash`, never `phone_number` (which doesn't exist).

### Error Handling
- Invalid input: Increment `retry_count`, return error message
- Max retries exceeded: Send `retry_exceeded_message`, move to next step
- Opt-out detection: Check for STOP/UNSUBSCRIBE/CANCEL/END/QUIT keywords
- Log all SMS interactions with truncated hashes for debugging

## Privacy & Security Notes

### What We Store
- ✅ Phone hashes (SHA-256, non-reversible)
- ✅ Survey responses (name, zip, etc. as collected)
- ✅ Consent records (timestamps, given/declined)
- ❌ Plaintext phone numbers

### Data Deletion Requests
1. Obtain user's phone number (e.g., via support call)
2. Hash it: `PhoneHasher.hash_phone(phone_number)`
3. Query database by `phone_hash`
4. Delete session, responses, and opt-out records

### Security Checklist
- Twilio webhook signature verification enforced (middleware)
- SQL injection prevented (use SQLAlchemy ORM with parameterized queries)
- No secrets in logs or source code
- HTTPS-only in production (Fly.io config)
- Rate limiting per phone hash (Phase 9)

## Common Pitfalls

1. **Phone Number Handling:** Always hash immediately, never store plaintext
2. **Survey References:** All `next` step IDs must exist in the same survey
3. **Jinja2 Context:** Variables are only available after `store_as` has executed
4. **Locking:** Use `with_for_update()` for all session lookups to prevent double-texting races
5. **E.164 Format:** Twilio sends `+15551234567` format; don't strip the `+`
6. **Consent Flow:** New sessions start with consent request, not first survey question

## Testing Strategy

- **Unit tests:** Individual services in isolation (survey loader, validation, branching)
- **Integration tests:** Full webhook flow with test database
- **Race condition tests:** Concurrent requests to same phone hash must serialize
- **E2E tests:** Complete survey from consent to completion

Test fixtures in `tests/conftest.py` provide sample sessions with hashed phone numbers.

## Documentation References

- **Full implementation plan:** `plans/implementation-plan.md` (2600+ lines, all tasks detailed)
- **Survey format guide:** `surveys/README.md`
- **Quick start guide:** `QUICKSTART.md`
- **Phase 0 completion:** `PHASE0_COMPLETION.md`
