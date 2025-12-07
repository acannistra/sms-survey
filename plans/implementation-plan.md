# Implementation Plan: SMS Survey Engine

## Overview

This plan details the implementation of a lightweight, serverless SMS survey engine that processes incoming text messages via Twilio webhooks, maintains survey state in PostgreSQL, and dynamically loads survey definitions from git-versioned YAML files.

The system is designed for maintainability (non-technical staff can edit surveys), cost-efficiency (scale-to-zero on Fly.io), and robustness (pessimistic locking, retry logic, consent tracking).

---

## Technical Architecture

### Component Stack
- **Runtime:** Python 3.11+ with FastAPI
- **Database:** PostgreSQL (Fly.io managed) with SQLAlchemy + Alembic
- **Hosting:** Fly.io with scale-to-zero capability
- **Config:** YAML + Jinja2 for survey templates
- **SMS Provider:** Twilio with webhook signature verification

### Architecture Flow
1. User sends SMS → Twilio receives message
2. Twilio POSTs to FastAPI webhook (with signature)
3. FastAPI validates signature, retrieves session with `SELECT FOR UPDATE`
4. Engine loads YAML survey, validates input, determines next step
5. Updates database, renders TwiML response
6. Twilio sends next question to user

---

## Project Structure

```
sms-survey/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI application entry point
│   ├── config.py                  # Environment configuration
│   ├── models/
│   │   ├── __init__.py
│   │   ├── database.py            # SQLAlchemy base, engine, session
│   │   ├── session.py             # SurveySession model
│   │   ├── response.py            # SurveyResponse model
│   │   └── optout.py              # OptOut model
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── survey.py              # Pydantic models for YAML validation
│   │   └── twilio.py              # Pydantic models for Twilio requests
│   ├── services/
│   │   ├── __init__.py
│   │   ├── survey_loader.py      # YAML loading and validation
│   │   ├── survey_engine.py      # Core state machine logic
│   │   ├── twilio_client.py      # TwiML generation
│   │   └── validation.py         # Input validation (regex, choices)
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── webhook.py             # Twilio webhook endpoint
│   │   └── health.py              # Health check endpoint
│   └── middleware/
│       ├── __init__.py
│       └── twilio_auth.py         # Signature verification
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/                  # Migration files
├── surveys/
│   ├── example-survey.yaml        # Example survey definition
│   └── README.md                  # Survey YAML format documentation
├── tests/
│   ├── __init__.py
│   ├── conftest.py                # Pytest fixtures
│   ├── unit/
│   │   ├── test_survey_loader.py
│   │   ├── test_survey_engine.py
│   │   ├── test_validation.py
│   │   └── test_twilio_client.py
│   ├── integration/
│   │   ├── test_webhook_flow.py
│   │   └── test_database.py
│   └── fixtures/
│       ├── sample_survey.yaml
│       └── twilio_requests.json
├── .env.example
├── .gitignore
├── alembic.ini
├── Dockerfile
├── fly.toml
├── pyproject.toml                 # Poetry dependencies
├── poetry.lock
└── README.md
```

---

## Privacy & Security Architecture

### Phone Number Hashing

**Privacy Commitment:** "We don't store your phone number."

This system uses **one-way hashing** for all phone numbers, providing strong privacy guarantees:

#### How It Works
1. **Immediate Hashing:** Phone numbers from Twilio webhooks are hashed with SHA-256 immediately upon receipt
2. **Application Salt:** A secret `PHONE_HASH_SALT` is combined with each phone number before hashing
3. **Deterministic Lookups:** Same phone number always produces same hash, enabling session lookups
4. **Non-Reversible:** Hashes cannot be converted back to phone numbers (one-way only)

#### What We Store
- ✅ **Phone hashes** (64-character hex strings) - cannot be reversed to phone numbers
- ✅ **Survey responses** - first name, zip code, etc. as collected in surveys
- ✅ **Consent records** - when users opted in/out
- ❌ **NOT stored:** Plaintext phone numbers in database or logs

#### Privacy Benefits
- **Breach Mitigation:** Stolen database does not expose phone numbers
- **GDPR/Privacy Compliance:** Enhanced data protection posture
- **Supporter Trust:** Demonstrates respect for privacy
- **Advocacy Protection:** Important for political/sensitive campaigns

#### Security Notes
- **Salt Secrecy:** The `PHONE_HASH_SALT` must be kept secret and never committed to git
- **Salt Rotation:** Changing salt orphans existing sessions (cannot look them up). Plan migrations carefully.
- **Limited Keyspace:** Phone numbers have limited possibilities (~10B for US). Strong salt prevents rainbow table attacks.
- **Twilio Still Has Numbers:** Twilio's systems maintain plaintext numbers (required for SMS delivery). We control our database only.
- **Log Truncation:** Logs show only first 12 characters of hashes, never full hashes or plaintext numbers

#### Data Deletion Requests
If a user requests data deletion:
1. You'll need their phone number to hash it
2. Query by phone hash to find their records
3. Delete sessions, responses, and opt-out records
4. No way to "list all phone numbers" since we don't store them

---

## Database Schema

### Table: `survey_sessions`
Tracks active survey sessions for each phone number.

**Privacy Note:** Phone numbers are never stored in plaintext. We use SHA-256 one-way hashing with an application salt, enabling us to say "We don't store your phone number."

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PRIMARY KEY | Unique session identifier |
| `phone_hash` | VARCHAR(64) | NOT NULL, INDEX | SHA-256 hash of E.164 phone number (one-way, non-reversible) |
| `survey_id` | VARCHAR(100) | NOT NULL | Survey identifier from YAML filename |
| `survey_version` | VARCHAR(50) | NOT NULL | Git commit SHA for version tracking |
| `current_step` | VARCHAR(100) | NOT NULL | Current question ID in YAML |
| `consent_given` | BOOLEAN | NOT NULL, DEFAULT FALSE | Whether user consented to survey |
| `consent_timestamp` | TIMESTAMP | NULLABLE | When consent was given |
| `started_at` | TIMESTAMP | NOT NULL, DEFAULT NOW() | Session start time |
| `updated_at` | TIMESTAMP | NOT NULL, DEFAULT NOW() | Last activity timestamp |
| `completed_at` | TIMESTAMP | NULLABLE | Survey completion time |
| `retry_count` | INTEGER | NOT NULL, DEFAULT 0 | Failed validation attempts for current step |
| `context` | JSONB | NOT NULL, DEFAULT '{}' | Jinja2 template context (name, zip, etc.) |

**Indexes:**
- `idx_phone_hash_survey` on `(phone_hash, survey_id)` - Fast session lookup
- `idx_updated_at` on `updated_at` - Cleanup old sessions

**Constraints:**
- `UNIQUE(phone_hash, survey_id)` where `completed_at IS NULL` - One active session per survey

---

### Table: `survey_responses`
Stores all survey answers with full audit trail.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PRIMARY KEY | Unique response identifier |
| `session_id` | UUID | NOT NULL, FOREIGN KEY → survey_sessions(id) | Associated session |
| `step_id` | VARCHAR(100) | NOT NULL | Question ID from YAML |
| `response_text` | TEXT | NOT NULL | Raw user response |
| `stored_value` | TEXT | NULLABLE | Normalized/transformed value |
| `responded_at` | TIMESTAMP | NOT NULL, DEFAULT NOW() | When response was received |
| `is_valid` | BOOLEAN | NOT NULL | Whether response passed validation |

**Indexes:**
- `idx_session_step` on `(session_id, step_id)` - Retrieve answers for a session

---

### Table: `optouts`
Tracks users who opted out via STOP messages.

**Privacy Note:** Phone numbers are hashed, not stored in plaintext.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PRIMARY KEY | Unique opt-out identifier |
| `phone_hash` | VARCHAR(64) | NOT NULL, UNIQUE | SHA-256 hash of E.164 phone number |
| `opted_out_at` | TIMESTAMP | NOT NULL, DEFAULT NOW() | When user sent STOP |
| `last_message` | TEXT | NULLABLE | The exact message that triggered opt-out |

**Indexes:**
- `idx_phone_hash_optout` on `phone_hash` - Fast lookup for opt-out check

---

## Survey YAML Format

### Schema Definition

```yaml
# surveys/example-survey.yaml
survey:
  id: advocacy_intake
  name: "Public Lands Advocacy Intake"
  description: "Collect supporter information for advocacy campaigns"
  version: "1.0.0"

consent:
  step_id: consent_request
  text: |
    Hi! This is the Public Lands Coalition. We'd like to ask you a few quick
    questions (2 min) about protecting wilderness areas. Reply YES to start,
    or STOP to opt out.
  accept_values:
    - "YES"
    - "Y"
    - "YEAH"
    - "OK"
  decline_values:
    - "NO"
    - "N"
    - "STOP"
  decline_message: "No problem! Reply START anytime to begin. Reply STOP to opt out of all messages."

steps:
  - id: q_name
    text: "Great! What's your first name?"
    type: text
    validation:
      min_length: 1
      max_length: 50
      pattern: "^[A-Za-z\\s'-]+$"
    error_message: "Please enter a valid name (letters only)."
    store_as: name
    next: q_zip

  - id: q_zip
    text: "Thanks {{ name }}! What's your zip code?"
    type: regex
    validation:
      pattern: "^\\d{5}$"
    error_message: "Please enter a 5-digit zip code."
    store_as: zip_code
    next: q_volunteer

  - id: q_volunteer
    text: "Would you like to volunteer for local events? Reply 1 for YES or 2 for NO."
    type: choice
    validation:
      choices:
        - value: "1"
          label: "YES"
          store_as: true
        - value: "2"
          label: "NO"
          store_as: false
    error_message: "Please reply 1 for YES or 2 for NO."
    store_as: wants_to_volunteer
    next: q_issues_conditional

  - id: q_issues_conditional
    text: "What issues matter most to you? Reply with keywords (e.g., wildlife, trails, water)."
    type: text
    validation:
      max_length: 160
    store_as: priority_issues
    # Conditional branching
    next_conditional:
      - condition: "wants_to_volunteer == true"
        next: q_email
      - condition: "wants_to_volunteer == false"
        next: thank_you

  - id: q_email
    text: "Last question! What's your email so we can send volunteer opportunities?"
    type: regex
    validation:
      pattern: "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$"
    error_message: "Please enter a valid email address."
    store_as: email
    next: thank_you

  - id: thank_you
    text: |
      Thank you {{ name }}! Your voice helps protect our public lands.
      We'll be in touch soon. Reply STOP anytime to opt out.
    type: terminal
    # No 'next' field - survey ends here

settings:
  max_retry_attempts: 3
  retry_exceeded_message: "We're having trouble understanding your response. Please call us at 555-0100 for assistance."
  timeout_hours: 48  # Auto-expire sessions after 48 hours of inactivity
```

### Validation Rules
- **text:** Free-form text with optional min/max length and regex pattern
- **regex:** Must match provided pattern exactly
- **choice:** Must match one of the enumerated values
- **terminal:** Final step with no next step

### Jinja2 Context
- All `store_as` values are available in subsequent step templates
- Use `{{ variable_name }}` syntax for interpolation
- Context is stored in `survey_sessions.context` JSONB column

---

## Implementation Phases

### Phase 0: Project Setup & Infrastructure (Day 1)

#### Task 0.1: Initialize Python Project
**Details:**
- Use Poetry for dependency management
- Configure Python 3.11+ virtual environment
- Add core dependencies: FastAPI, SQLAlchemy, Alembic, Pydantic, Jinja2, PyYAML, twilio, pytest

**Files:**
- Create `/Users/tony/Dropbox/Projects/sms-survey/pyproject.toml`
- Create `/Users/tony/Dropbox/Projects/sms-survey/poetry.lock`

**Dependencies:** None

**Testing:**
```bash
poetry install
poetry run python --version  # Should show 3.11+
```

---

#### Task 0.2: Configure Environment Variables
**Details:**
- Create `.env.example` with all required configuration
- Document each environment variable with comments
- Add `.env` to `.gitignore`

**Environment Variables:**
```bash
# Database
DATABASE_URL=postgresql://user:pass@host:5432/sms_survey
DATABASE_POOL_SIZE=5
DATABASE_MAX_OVERFLOW=10

# Twilio
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_PHONE_NUMBER=+15551234567

# Application
ENVIRONMENT=development  # development, staging, production
LOG_LEVEL=INFO
SURVEYS_DIR=/app/surveys
GIT_COMMIT_SHA=${FLY_IMAGE_REF:-local}

# Security
SECRET_KEY=generate-with-secrets-token-hex-32
ALLOWED_ORIGINS=https://yourdomain.com

# Privacy: Phone Number Hashing
# CRITICAL: This salt enables "We don't store your phone number" privacy claim
# - Must be kept secret and never committed to git
# - Changing this will orphan all existing sessions (cannot look them up)
# - Generate with: openssl rand -hex 64
# - Should be rotated periodically (e.g., annually) with migration plan
PHONE_HASH_SALT=generate-with-openssl-rand-hex-64-KEEP-SECRET
```

**Files:**
- Create `/Users/tony/Dropbox/Projects/sms-survey/.env.example`
- Create `/Users/tony/Dropbox/Projects/sms-survey/.gitignore`

**Dependencies:** None

**Testing:** Manual review of `.env.example`

---

#### Task 0.3: Create Application Configuration Module
**Details:**
- Create `app/config.py` using Pydantic Settings
- Load environment variables with validation
- Provide sensible defaults for development

**Files:**
- Create `/Users/tony/Dropbox/Projects/sms-survey/app/config.py`

**Code Structure:**
```python
from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache

class Settings(BaseSettings):
    # Database
    database_url: str
    database_pool_size: int = 5

    # Twilio
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_phone_number: str

    # Application
    environment: str = "development"
    log_level: str = "INFO"
    surveys_dir: str = "./surveys"
    git_commit_sha: str = "local"

    # Privacy: Phone Number Hashing
    phone_hash_salt: str = Field(
        ...,
        description="Secret salt for one-way hashing of phone numbers. MUST be kept secret."
    )

    class Config:
        env_file = ".env"

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

**Dependencies:** Task 0.1 (Poetry setup)

**Testing:**
```python
from app.config import get_settings
settings = get_settings()
assert settings.database_url is not None
```

---

#### Task 0.4: Setup Directory Structure
**Details:**
- Create all necessary directories as outlined in Project Structure
- Add `__init__.py` files to make Python packages
- Create placeholder README files

**Files:**
- Create all directories from project structure
- Create all `__init__.py` files

**Dependencies:** Task 0.1

**Testing:**
```bash
tree app/  # Verify structure matches plan
```

---

#### Task 0.5: Configure Logging
**Details:**
- Setup structured logging with JSON format for production
- Configure log levels based on environment
- Add request ID tracking for debugging

**Files:**
- Create `/Users/tony/Dropbox/Projects/sms-survey/app/logging_config.py`

**Dependencies:** Task 0.3 (config module)

**Testing:**
```python
import logging
logger = logging.getLogger(__name__)
logger.info("Test log message", extra={"key": "value"})
```

---

#### Task 0.6: Create Phone Number Hashing Service
**Details:**
- Create service for one-way hashing of phone numbers
- Use SHA-256 with application salt
- Enable privacy claim: "We don't store your phone number"
- Normalize phone numbers to E.164 format before hashing
- Deterministic hashing allows session lookups without storing plaintext

**Files:**
- Create `/Users/tony/Dropbox/Projects/sms-survey/app/services/phone_hasher.py`

**Code Structure:**
```python
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
    """

    @staticmethod
    def normalize_e164(phone: str) -> str:
        """
        Normalize phone number to E.164 format.
        Twilio sends numbers in E.164, so this mainly strips whitespace.
        """
        return phone.strip()

    @staticmethod
    def hash_phone(phone: str) -> str:
        """
        One-way hash of phone number with application salt.

        Args:
            phone: Phone number in E.164 format (e.g., +15551234567)

        Returns:
            64-character hex string (SHA-256 hash)
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
        Full hashes should not appear in logs.
        """
        return f"{phone_hash[:12]}..."

# Usage in webhook:
# from app.services.phone_hasher import PhoneHasher
# phone_hash = PhoneHasher.hash_phone(request.From)
```

**Dependencies:** Task 0.3 (config module)

**Testing:**
```python
from app.services.phone_hasher import PhoneHasher

# Test deterministic hashing
hash1 = PhoneHasher.hash_phone("+15551234567")
hash2 = PhoneHasher.hash_phone("+15551234567")
assert hash1 == hash2  # Same input = same hash

# Test hash format
assert len(hash1) == 64  # SHA-256 hex = 64 chars
assert all(c in '0123456789abcdef' for c in hash1)

# Test normalization
assert PhoneHasher.normalize_e164(" +15551234567 ") == "+15551234567"

# Test truncation for logging
truncated = PhoneHasher.truncate_for_logging(hash1)
assert len(truncated) == 15  # 12 chars + "..."
```

---

### Phase 1: Database Layer (Day 1-2)

#### Task 1.1: Setup SQLAlchemy Base and Engine
**Details:**
- Create database connection management
- Configure connection pooling
- Add async support for FastAPI

**Files:**
- Create `/Users/tony/Dropbox/Projects/sms-survey/app/models/database.py`

**Code Structure:**
```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import QueuePool
from app.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url,
    poolclass=QueuePool,
    pool_size=settings.database_pool_size,
    max_overflow=10,
    pool_pre_ping=True,  # Verify connections before using
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    """FastAPI dependency for database sessions"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

**Dependencies:** Task 0.3 (config)

**Testing:**
```python
from app.models.database import engine
with engine.connect() as conn:
    result = conn.execute("SELECT 1")
    assert result.scalar() == 1
```

---

#### Task 1.2: Create SurveySession Model
**Details:**
- Implement SQLAlchemy model matching schema design
- Add relationship mappings to responses
- Include helper methods for state transitions

**Files:**
- Create `/Users/tony/Dropbox/Projects/sms-survey/app/models/session.py`

**Code Structure:**
```python
from sqlalchemy import Column, String, Boolean, Integer, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.models.database import Base

class SurveySession(Base):
    __tablename__ = "survey_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone_hash = Column(String(64), nullable=False, index=True, comment="SHA-256 hash of phone number")
    survey_id = Column(String(100), nullable=False)
    survey_version = Column(String(50), nullable=False)
    current_step = Column(String(100), nullable=False)
    consent_given = Column(Boolean, nullable=False, default=False)
    consent_timestamp = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    context = Column(JSONB, nullable=False, default=dict)

    # Relationships
    responses = relationship("SurveyResponse", back_populates="session", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        Index('idx_phone_hash_survey', 'phone_hash', 'survey_id'),
        Index('idx_updated_at', 'updated_at'),
    )

    def increment_retry(self):
        """Increment retry counter for current step"""
        self.retry_count += 1

    def reset_retry(self):
        """Reset retry counter when moving to new step"""
        self.retry_count = 0

    def advance_step(self, next_step_id: str):
        """Move to next step and reset retry counter"""
        self.current_step = next_step_id
        self.reset_retry()
        self.updated_at = datetime.utcnow()
```

**Dependencies:** Task 1.1

**Testing:** Will be tested via Alembic migration and unit tests

---

#### Task 1.3: Create SurveyResponse Model
**Details:**
- Implement response storage model
- Add foreign key to survey_sessions
- Include validation status tracking

**Files:**
- Create `/Users/tony/Dropbox/Projects/sms-survey/app/models/response.py`

**Code Structure:**
```python
from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.models.database import Base

class SurveyResponse(Base):
    __tablename__ = "survey_responses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey('survey_sessions.id'), nullable=False)
    step_id = Column(String(100), nullable=False)
    response_text = Column(Text, nullable=False)
    stored_value = Column(Text, nullable=True)
    responded_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    is_valid = Column(Boolean, nullable=False)

    # Relationships
    session = relationship("SurveySession", back_populates="responses")

    # Indexes
    __table_args__ = (
        Index('idx_session_step', 'session_id', 'step_id'),
    )
```

**Dependencies:** Task 1.2

**Testing:** Will be tested via Alembic migration and unit tests

---

#### Task 1.4: Create OptOut Model
**Details:**
- Implement opt-out tracking
- Ensure phone number uniqueness
- Add lookup helper methods

**Files:**
- Create `/Users/tony/Dropbox/Projects/sms-survey/app/models/optout.py`

**Code Structure:**
```python
from sqlalchemy import Column, String, Text, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid
from app.models.database import Base

class OptOut(Base):
    __tablename__ = "optouts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone_hash = Column(String(64), nullable=False, unique=True, index=True, comment="SHA-256 hash of phone number")
    opted_out_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_message = Column(Text, nullable=True)

    @classmethod
    def is_opted_out(cls, db, phone_hash: str) -> bool:
        """Check if phone hash has opted out"""
        return db.query(cls).filter(cls.phone_hash == phone_hash).first() is not None
```

**Dependencies:** Task 1.1

**Testing:** Unit test for `is_opted_out` method

---

#### Task 1.5: Configure Alembic for Migrations
**Details:**
- Initialize Alembic in project
- Configure `alembic.ini` with database URL from environment
- Setup `env.py` to import all models

**Files:**
- Create `/Users/tony/Dropbox/Projects/sms-survey/alembic.ini`
- Create `/Users/tony/Dropbox/Projects/sms-survey/alembic/env.py`

**Alembic Configuration:**
```python
# alembic/env.py
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
from app.config import get_settings
from app.models.database import Base
# Import all models so Alembic can detect them
from app.models.session import SurveySession
from app.models.response import SurveyResponse
from app.models.optout import OptOut

config = context.config
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata

def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
```

**Dependencies:** Tasks 1.2, 1.3, 1.4

**Testing:**
```bash
poetry run alembic check  # Verify configuration
```

---

#### Task 1.6: Create Initial Migration
**Details:**
- Generate initial migration with all three tables
- Review generated SQL for correctness
- Test migration up and down

**Files:**
- Create `/Users/tony/Dropbox/Projects/sms-survey/alembic/versions/001_initial_schema.py`

**Dependencies:** Task 1.5

**Testing:**
```bash
# Generate migration
poetry run alembic revision --autogenerate -m "Initial schema"

# Apply migration
poetry run alembic upgrade head

# Verify tables exist
psql $DATABASE_URL -c "\dt"

# Test rollback
poetry run alembic downgrade -1
poetry run alembic upgrade head
```

---

### Phase 2: Survey Definition & Loading (Day 2)

#### Task 2.1: Create Pydantic Survey Schema
**Details:**
- Define Pydantic models for YAML validation
- Support all question types (text, regex, choice)
- Include conditional branching logic
- Validate nested structures

**Files:**
- Create `/Users/tony/Dropbox/Projects/sms-survey/app/schemas/survey.py`

**Code Structure:**
```python
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any, Literal

class ValidationRules(BaseModel):
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    pattern: Optional[str] = None
    choices: Optional[List[Dict[str, Any]]] = None

class ConditionalNext(BaseModel):
    condition: str  # Python expression evaluated with context
    next: str       # Next step ID if condition is true

class SurveyStep(BaseModel):
    id: str
    text: str
    type: Literal["text", "regex", "choice", "terminal"]
    validation: Optional[ValidationRules] = None
    error_message: Optional[str] = "Invalid response. Please try again."
    store_as: Optional[str] = None
    next: Optional[str] = None  # Simple next step
    next_conditional: Optional[List[ConditionalNext]] = None  # Conditional branching

    @validator('next', 'next_conditional')
    def validate_next_logic(cls, v, values, field):
        step_type = values.get('type')
        # Terminal steps should not have 'next'
        if step_type == 'terminal' and v is not None:
            raise ValueError("Terminal steps cannot have 'next' or 'next_conditional'")
        # Non-terminal steps must have next logic
        if step_type != 'terminal' and v is None and values.get('next_conditional') is None:
            raise ValueError("Non-terminal steps must have 'next' or 'next_conditional'")
        return v

class ConsentConfig(BaseModel):
    step_id: str
    text: str
    accept_values: List[str]
    decline_values: List[str]
    decline_message: str

class SurveySettings(BaseModel):
    max_retry_attempts: int = 3
    retry_exceeded_message: str = "We're having trouble. Please contact us for help."
    timeout_hours: int = 48

class SurveyMetadata(BaseModel):
    id: str
    name: str
    description: str
    version: str

class Survey(BaseModel):
    survey: SurveyMetadata
    consent: ConsentConfig
    steps: List[SurveyStep]
    settings: SurveySettings = SurveySettings()

    @validator('steps')
    def validate_step_references(cls, steps):
        """Ensure all 'next' references point to valid step IDs"""
        step_ids = {step.id for step in steps}
        for step in steps:
            if step.next and step.next not in step_ids:
                raise ValueError(f"Step '{step.id}' references unknown next step '{step.next}'")
            if step.next_conditional:
                for cond in step.next_conditional:
                    if cond.next not in step_ids:
                        raise ValueError(f"Conditional in step '{step.id}' references unknown step '{cond.next}'")
        return steps
```

**Dependencies:** Task 0.1 (Poetry setup)

**Testing:** Unit tests with valid and invalid YAML structures

---

#### Task 2.2: Implement Survey Loader Service
**Details:**
- Load YAML files from `surveys/` directory
- Parse and validate against Pydantic schema
- Cache loaded surveys in memory
- Track Git commit SHA for versioning

**Files:**
- Create `/Users/tony/Dropbox/Projects/sms-survey/app/services/survey_loader.py`

**Code Structure:**
```python
import yaml
from pathlib import Path
from functools import lru_cache
from typing import Dict
from app.schemas.survey import Survey
from app.config import get_settings

class SurveyLoader:
    def __init__(self, surveys_dir: str):
        self.surveys_dir = Path(surveys_dir)
        self._cache: Dict[str, Survey] = {}

    def load_survey(self, survey_id: str) -> Survey:
        """Load and validate survey from YAML file"""
        if survey_id in self._cache:
            return self._cache[survey_id]

        survey_path = self.surveys_dir / f"{survey_id}.yaml"
        if not survey_path.exists():
            raise FileNotFoundError(f"Survey not found: {survey_id}")

        with open(survey_path, 'r') as f:
            raw_yaml = yaml.safe_load(f)

        # Validate with Pydantic
        survey = Survey(**raw_yaml)
        self._cache[survey_id] = survey
        return survey

    def list_surveys(self) -> list[str]:
        """List all available survey IDs"""
        return [p.stem for p in self.surveys_dir.glob("*.yaml")]

    def get_step(self, survey_id: str, step_id: str):
        """Get a specific step from a survey"""
        survey = self.load_survey(survey_id)
        for step in survey.steps:
            if step.id == step_id:
                return step
        raise ValueError(f"Step '{step_id}' not found in survey '{survey_id}'")

@lru_cache
def get_survey_loader() -> SurveyLoader:
    settings = get_settings()
    return SurveyLoader(settings.surveys_dir)
```

**Dependencies:** Task 2.1

**Testing:**
```python
loader = get_survey_loader()
survey = loader.load_survey("example-survey")
assert survey.survey.id == "advocacy_intake"
```

---

#### Task 2.3: Implement Input Validation Service
**Details:**
- Validate user input against step validation rules
- Support regex patterns, choice matching, length constraints
- Normalize input (trim whitespace, uppercase for choices)
- Return validation results with error messages

**Files:**
- Create `/Users/tony/Dropbox/Projects/sms-survey/app/services/validation.py`

**Code Structure:**
```python
import re
from typing import Tuple, Optional
from app.schemas.survey import SurveyStep, ValidationRules

class ValidationResult:
    def __init__(self, is_valid: bool, normalized_value: Optional[str] = None, error: Optional[str] = None):
        self.is_valid = is_valid
        self.normalized_value = normalized_value
        self.error = error

class InputValidator:
    @staticmethod
    def validate(step: SurveyStep, user_input: str) -> ValidationResult:
        """Validate user input against step validation rules"""
        # Normalize input
        normalized = user_input.strip()

        if not step.validation:
            return ValidationResult(is_valid=True, normalized_value=normalized)

        rules = step.validation

        # Length validation
        if rules.min_length and len(normalized) < rules.min_length:
            return ValidationResult(is_valid=False, error=f"Response must be at least {rules.min_length} characters")

        if rules.max_length and len(normalized) > rules.max_length:
            return ValidationResult(is_valid=False, error=f"Response must be no more than {rules.max_length} characters")

        # Pattern validation (for regex and text types)
        if rules.pattern:
            if not re.match(rules.pattern, normalized):
                return ValidationResult(is_valid=False, error=step.error_message)

        # Choice validation
        if rules.choices:
            normalized_upper = normalized.upper()
            for choice in rules.choices:
                if normalized_upper == str(choice['value']).upper():
                    # Return the stored value, not the user's input
                    stored = choice.get('store_as', choice['value'])
                    return ValidationResult(is_valid=True, normalized_value=str(stored))
            return ValidationResult(is_valid=False, error=step.error_message)

        return ValidationResult(is_valid=True, normalized_value=normalized)
```

**Dependencies:** Task 2.1

**Testing:** Unit tests for each validation type (regex, choice, length)

---

#### Task 2.4: Create Example Survey YAML
**Details:**
- Create a complete example survey matching the schema
- Include all question types
- Demonstrate conditional branching
- Add inline comments for documentation

**Files:**
- Create `/Users/tony/Dropbox/Projects/sms-survey/surveys/example-survey.yaml`

**Dependencies:** Task 2.1 (schema definition)

**Testing:** Load with SurveyLoader and validate all steps

---

#### Task 2.5: Create Survey YAML Documentation
**Details:**
- Document YAML format with examples
- Explain each field and validation type
- Provide conditional branching examples
- Add troubleshooting section

**Files:**
- Create `/Users/tony/Dropbox/Projects/sms-survey/surveys/README.md`

**Content Outline:**
1. Survey YAML Structure
2. Question Types (text, regex, choice, terminal)
3. Validation Rules
4. Conditional Branching Syntax
5. Jinja2 Template Variables
6. Best Practices
7. Common Errors and Solutions

**Dependencies:** Task 2.4

**Testing:** Manual review by non-technical stakeholder

---

### Phase 3: Survey Engine Core Logic (Day 2-3)

#### Task 3.1: Implement Jinja2 Template Renderer
**Details:**
- Create service to render step text with context variables
- Configure Jinja2 environment with safe defaults
- Handle missing variables gracefully
- Add custom filters if needed

**Files:**
- Create `/Users/tony/Dropbox/Projects/sms-survey/app/services/template_renderer.py`

**Code Structure:**
```python
from jinja2 import Environment, BaseLoader, TemplateError
from typing import Dict, Any

class TemplateRenderer:
    def __init__(self):
        self.env = Environment(
            loader=BaseLoader(),
            autoescape=True,
            undefined=jinja2.StrictUndefined  # Raise error on undefined variables
        )

    def render(self, template_text: str, context: Dict[str, Any]) -> str:
        """Render Jinja2 template with context variables"""
        try:
            template = self.env.from_string(template_text)
            return template.render(**context)
        except TemplateError as e:
            raise ValueError(f"Template rendering error: {str(e)}")

def get_template_renderer() -> TemplateRenderer:
    return TemplateRenderer()
```

**Dependencies:** Task 0.1

**Testing:**
```python
renderer = get_template_renderer()
result = renderer.render("Hello {{ name }}!", {"name": "Alice"})
assert result == "Hello Alice!"
```

---

#### Task 3.2: Implement Conditional Branching Logic
**Details:**
- Evaluate Python expressions from `next_conditional`
- Use context variables for expression evaluation
- Implement safe expression evaluation (no arbitrary code execution)
- Return next step ID based on first matching condition

**Files:**
- Create `/Users/tony/Dropbox/Projects/sms-survey/app/services/branching.py`

**Code Structure:**
```python
from typing import Dict, Any, Optional
from app.schemas.survey import SurveyStep

class BranchingEngine:
    @staticmethod
    def evaluate_condition(condition: str, context: Dict[str, Any]) -> bool:
        """Safely evaluate condition expression with context"""
        # Use restricted globals for safety
        allowed_globals = {
            "__builtins__": {
                "True": True,
                "False": False,
                "None": None,
            }
        }
        try:
            result = eval(condition, allowed_globals, context)
            return bool(result)
        except Exception as e:
            raise ValueError(f"Invalid condition '{condition}': {str(e)}")

    @staticmethod
    def determine_next_step(step: SurveyStep, context: Dict[str, Any]) -> Optional[str]:
        """Determine next step based on conditional logic"""
        # Check conditional branching first
        if step.next_conditional:
            for conditional in step.next_conditional:
                if BranchingEngine.evaluate_condition(conditional.condition, context):
                    return conditional.next

        # Fall back to simple next
        return step.next
```

**Dependencies:** Task 2.1

**Testing:** Unit tests with various conditional expressions

---

#### Task 3.3: Implement Core Survey Engine
**Details:**
- Orchestrate survey flow (load survey, validate input, determine next step)
- Manage session state transitions
- Handle consent workflow
- Implement retry logic with max attempts
- Update context with stored values

**Files:**
- Create `/Users/tony/Dropbox/Projects/sms-survey/app/services/survey_engine.py`

**Code Structure:**
```python
from sqlalchemy.orm import Session
from app.models.session import SurveySession
from app.models.response import SurveyResponse
from app.services.survey_loader import get_survey_loader
from app.services.validation import InputValidator
from app.services.branching import BranchingEngine
from app.services.template_renderer import get_template_renderer

class SurveyEngine:
    def __init__(self, db: Session):
        self.db = db
        self.loader = get_survey_loader()
        self.validator = InputValidator()
        self.branching = BranchingEngine()
        self.renderer = get_template_renderer()

    def process_message(self, session: SurveySession, user_input: str) -> tuple[str, bool]:
        """
        Process incoming message and return (response_text, is_complete)

        Returns:
            - response_text: Message to send back to user
            - is_complete: Whether survey is complete
        """
        survey = self.loader.load_survey(session.survey_id)

        # Handle consent step
        if not session.consent_given:
            return self._handle_consent(session, survey, user_input)

        # Get current step
        current_step = self.loader.get_step(session.survey_id, session.current_step)

        # Validate input
        validation_result = self.validator.validate(current_step, user_input)

        # Store response
        response = SurveyResponse(
            session_id=session.id,
            step_id=current_step.id,
            response_text=user_input,
            stored_value=validation_result.normalized_value,
            is_valid=validation_result.is_valid
        )
        self.db.add(response)

        if not validation_result.is_valid:
            session.increment_retry()

            # Check if max retries exceeded
            if session.retry_count >= survey.settings.max_retry_attempts:
                session.retry_count = 0
                return survey.settings.retry_exceeded_message, False

            return validation_result.error or current_step.error_message, False

        # Valid response - update context
        if current_step.store_as:
            session.context[current_step.store_as] = validation_result.normalized_value

        session.reset_retry()

        # Check if terminal step
        if current_step.type == "terminal":
            session.completed_at = datetime.utcnow()
            rendered_text = self.renderer.render(current_step.text, session.context)
            return rendered_text, True

        # Determine next step
        next_step_id = self.branching.determine_next_step(current_step, session.context)
        session.advance_step(next_step_id)

        # Get next step and render
        next_step = self.loader.get_step(session.survey_id, next_step_id)
        rendered_text = self.renderer.render(next_step.text, session.context)

        return rendered_text, False

    def _handle_consent(self, session: SurveySession, survey, user_input: str) -> tuple[str, bool]:
        """Handle consent request/response"""
        consent = survey.consent
        normalized_input = user_input.strip().upper()

        # Check if user declined
        if normalized_input in [v.upper() for v in consent.decline_values]:
            session.completed_at = datetime.utcnow()
            return consent.decline_message, True

        # Check if user accepted
        if normalized_input in [v.upper() for v in consent.accept_values]:
            session.consent_given = True
            session.consent_timestamp = datetime.utcnow()

            # Start first step
            first_step = survey.steps[0]
            session.current_step = first_step.id

            rendered_text = self.renderer.render(first_step.text, session.context)
            return rendered_text, False

        # Invalid consent response
        return consent.text, False
```

**Dependencies:** Tasks 2.2, 2.3, 3.1, 3.2

**Testing:** Integration tests with mock database sessions

---

### Phase 4: Twilio Integration (Day 3)

#### Task 4.1: Create Twilio Request Schema
**Details:**
- Define Pydantic models for incoming Twilio webhook data
- Include all relevant fields (From, To, Body, MessageSid, etc.)
- Add validation for E.164 phone format

**Files:**
- Create `/Users/tony/Dropbox/Projects/sms-survey/app/schemas/twilio.py`

**Code Structure:**
```python
from pydantic import BaseModel, Field, validator

class TwilioWebhookRequest(BaseModel):
    MessageSid: str
    AccountSid: str
    From: str  # E.164 format: +15551234567
    To: str
    Body: str
    NumMedia: str = "0"

    @validator('From', 'To')
    def validate_e164_format(cls, v):
        if not v.startswith('+'):
            raise ValueError("Phone number must be in E.164 format")
        return v
```

**Dependencies:** Task 0.1

**Testing:** Unit tests with sample Twilio payloads

---

#### Task 4.2: Implement TwiML Response Generator
**Details:**
- Create service to generate TwiML XML responses
- Support simple message responses
- Add helper methods for common response patterns

**Files:**
- Create `/Users/tony/Dropbox/Projects/sms-survey/app/services/twilio_client.py`

**Code Structure:**
```python
from twilio.twiml.messaging_response import MessagingResponse

class TwilioClient:
    @staticmethod
    def create_response(message: str) -> str:
        """Generate TwiML response with message"""
        response = MessagingResponse()
        response.message(message)
        return str(response)

    @staticmethod
    def create_empty_response() -> str:
        """Generate empty TwiML response (no message sent)"""
        response = MessagingResponse()
        return str(response)
```

**Dependencies:** Task 0.1 (Twilio SDK)

**Testing:**
```python
twiml = TwilioClient.create_response("Hello!")
assert "<Message>Hello!</Message>" in twiml
```

---

#### Task 4.3: Implement Twilio Signature Verification Middleware
**Details:**
- Create FastAPI middleware to verify Twilio request signatures
- Reject requests with invalid signatures
- Log security events

**Files:**
- Create `/Users/tony/Dropbox/Projects/sms-survey/app/middleware/twilio_auth.py`

**Code Structure:**
```python
from fastapi import Request, HTTPException, status
from twilio.request_validator import RequestValidator
from app.config import get_settings
import logging

logger = logging.getLogger(__name__)

class TwilioSignatureValidator:
    def __init__(self):
        settings = get_settings()
        self.validator = RequestValidator(settings.twilio_auth_token)

    async def verify_request(self, request: Request) -> bool:
        """Verify Twilio request signature"""
        # Get signature from header
        signature = request.headers.get('X-Twilio-Signature', '')

        # Get full URL
        url = str(request.url)

        # Get form data
        form_data = await request.form()
        params = dict(form_data)

        # Validate signature
        is_valid = self.validator.validate(url, params, signature)

        if not is_valid:
            logger.warning(f"Invalid Twilio signature from {request.client.host}")

        return is_valid

async def verify_twilio_signature(request: Request):
    """FastAPI dependency for signature verification"""
    validator = TwilioSignatureValidator()
    if not await validator.verify_request(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Twilio signature"
        )
```

**Dependencies:** Task 0.3, Task 4.1

**Testing:** Unit tests with valid and invalid signatures

---

### Phase 5: FastAPI Routes & Application (Day 3-4)

#### Task 5.1: Create Health Check Endpoint
**Details:**
- Simple endpoint for Fly.io health checks
- Return 200 OK if app is running
- Include database connectivity check

**Files:**
- Create `/Users/tony/Dropbox/Projects/sms-survey/app/routes/health.py`

**Code Structure:**
```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.models.database import get_db

router = APIRouter()

@router.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Health check endpoint for Fly.io"""
    # Test database connection
    try:
        db.execute("SELECT 1")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)}
```

**Dependencies:** Task 1.1

**Testing:**
```bash
curl http://localhost:8000/health
```

---

#### Task 5.2: Create Webhook Endpoint with Session Management
**Details:**
- Implement main Twilio webhook endpoint
- Handle opt-out detection (STOP, UNSUBSCRIBE, etc.)
- Retrieve or create survey session with pessimistic locking
- Process message through survey engine
- Return TwiML response

**Files:**
- Create `/Users/tony/Dropbox/Projects/sms-survey/app/routes/webhook.py`

**Code Structure:**
```python
from fastapi import APIRouter, Depends, Form, Response
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.database import get_db
from app.models.session import SurveySession
from app.models.optout import OptOut
from app.schemas.twilio import TwilioWebhookRequest
from app.services.survey_engine import SurveyEngine
from app.services.twilio_client import TwilioClient
from app.middleware.twilio_auth import verify_twilio_signature
from app.config import get_settings
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# Common opt-out keywords
OPT_OUT_KEYWORDS = {"STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "QUIT"}

@router.post("/webhook/sms", dependencies=[Depends(verify_twilio_signature)])
async def handle_sms_webhook(
    MessageSid: str = Form(...),
    From: str = Form(...),
    To: str = Form(...),
    Body: str = Form(...),
    db: Session = Depends(get_db)
):
    """Handle incoming SMS from Twilio"""
    settings = get_settings()

    # Hash phone number immediately for privacy
    from app.services.phone_hasher import PhoneHasher
    phone_hash = PhoneHasher.hash_phone(From)
    message_body = Body.strip()

    # Log with truncated hash (never log plaintext phone or full hash)
    logger.info(f"Received SMS from {PhoneHasher.truncate_for_logging(phone_hash)}: {message_body}")

    # Check for opt-out
    if message_body.upper() in OPT_OUT_KEYWORDS:
        # Record opt-out
        existing_optout = db.query(OptOut).filter(OptOut.phone_hash == phone_hash).first()
        if not existing_optout:
            optout = OptOut(phone_hash=phone_hash, last_message=message_body)
            db.add(optout)
            db.commit()

        response_text = "You have been unsubscribed. You will not receive any more messages from us. Reply START to resubscribe."
        return Response(content=TwilioClient.create_response(response_text), media_type="application/xml")

    # Check if user has opted out
    if OptOut.is_opted_out(db, phone_hash):
        logger.info(f"Ignoring message from opted-out user: {PhoneHasher.truncate_for_logging(phone_hash)}")
        return Response(content=TwilioClient.create_empty_response(), media_type="application/xml")

    # Get or create survey session with pessimistic locking
    # Assuming default survey_id - in production, this might come from routing logic
    survey_id = "example-survey"

    session = db.query(SurveySession).filter(
        SurveySession.phone_hash == phone_hash,
        SurveySession.survey_id == survey_id,
        SurveySession.completed_at == None
    ).with_for_update().first()

    if not session:
        # Create new session
        from app.services.survey_loader import get_survey_loader
        loader = get_survey_loader()
        survey = loader.load_survey(survey_id)

        session = SurveySession(
            phone_hash=phone_hash,
            survey_id=survey_id,
            survey_version=settings.git_commit_sha,
            current_step=survey.consent.step_id,
            consent_given=False,
            context={}
        )
        db.add(session)
        db.flush()  # Get session ID

        # Send consent message
        response_text = survey.consent.text
    else:
        # Process message through engine
        engine = SurveyEngine(db)
        response_text, is_complete = engine.process_message(session, message_body)

    db.commit()

    logger.info(f"Responding to {PhoneHasher.truncate_for_logging(phone_hash)}: {response_text}")

    return Response(content=TwilioClient.create_response(response_text), media_type="application/xml")
```

**Dependencies:** Tasks 1.2, 1.4, 3.3, 4.2, 4.3

**Testing:** Integration tests with mock Twilio requests

---

#### Task 5.3: Create FastAPI Application with Middleware
**Details:**
- Initialize FastAPI application
- Register routes
- Add CORS middleware if needed
- Configure exception handlers
- Setup startup/shutdown events

**Files:**
- Create `/Users/tony/Dropbox/Projects/sms-survey/app/main.py`

**Code Structure:**
```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.routes import webhook, health
from app.config import get_settings
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="SMS Survey Engine",
    description="Lightweight SMS survey platform with Twilio integration",
    version="1.0.0"
)

# Register routes
app.include_router(health.router, tags=["health"])
app.include_router(webhook.router, prefix="/api", tags=["webhook"])

# Exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

@app.on_event("startup")
async def startup_event():
    settings = get_settings()
    logger.info(f"Starting SMS Survey Engine (env: {settings.environment})")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down SMS Survey Engine")
```

**Dependencies:** Tasks 5.1, 5.2

**Testing:**
```bash
poetry run uvicorn app.main:app --reload
curl http://localhost:8000/health
```

---

### Phase 6: Deployment Configuration (Day 4)

#### Task 6.1: Create Dockerfile
**Details:**
- Multi-stage build for optimized image size
- Use Python 3.11+ slim base image
- Install dependencies via Poetry
- Set up non-root user for security
- Configure for Fly.io deployment

**Files:**
- Create `/Users/tony/Dropbox/Projects/sms-survey/Dockerfile`

**Code Structure:**
```dockerfile
# Build stage
FROM python:3.11-slim as builder

WORKDIR /app

# Install poetry
RUN pip install poetry==1.7.1

# Copy dependency files
COPY pyproject.toml poetry.lock ./

# Install dependencies
RUN poetry config virtualenvs.create false \
    && poetry install --no-dev --no-interaction --no-ansi

# Runtime stage
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY app/ ./app/
COPY surveys/ ./surveys/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Dependencies:** Task 0.1

**Testing:**
```bash
docker build -t sms-survey .
docker run -p 8000:8000 --env-file .env sms-survey
curl http://localhost:8000/health
```

---

#### Task 6.2: Create Fly.io Configuration
**Details:**
- Configure `fly.toml` with app settings
- Setup PostgreSQL database attachment
- Configure scale-to-zero settings
- Add release command for migrations
- Configure health checks

**Files:**
- Create `/Users/tony/Dropbox/Projects/sms-survey/fly.toml`

**Code Structure:**
```toml
app = "sms-survey"
primary_region = "sea"  # Choose your region

[build]
  dockerfile = "Dockerfile"

[deploy]
  release_command = "alembic upgrade head"

[env]
  ENVIRONMENT = "production"
  LOG_LEVEL = "INFO"
  SURVEYS_DIR = "/app/surveys"

[http_service]
  internal_port = 8000
  force_https = true
  auto_stop_machines = true
  auto_start_machines = true
  min_machines_running = 0  # Scale to zero

  [http_service.concurrency]
    type = "requests"
    soft_limit = 200
    hard_limit = 250

[[http_service.checks]]
  grace_period = "10s"
  interval = "30s"
  method = "GET"
  timeout = "5s"
  path = "/health"

[[vm]]
  cpu_kind = "shared"
  cpus = 1
  memory_mb = 256
```

**Dependencies:** Task 6.1

**Testing:** Deploy to Fly.io staging environment

---

#### Task 6.3: Create Deployment Documentation
**Details:**
- Document initial deployment steps
- Explain environment variable configuration
- Add database migration instructions
- Include rollback procedures

**Files:**
- Create `/Users/tony/Dropbox/Projects/sms-survey/DEPLOYMENT.md`

**Content Outline:**
1. Prerequisites (Fly.io CLI, PostgreSQL addon)
2. Initial Deployment Steps
3. Environment Variable Configuration
4. Database Setup and Migrations
5. Twilio Webhook Configuration
6. Monitoring and Logging
7. Rollback Procedures
8. Troubleshooting

**Dependencies:** Task 6.2

**Testing:** Manual review and dry-run deployment

---

### Phase 7: Testing Strategy (Day 4-5)

#### Task 7.1: Setup Test Infrastructure
**Details:**
- Configure pytest with fixtures
- Create test database setup/teardown
- Add test factories for models
- Configure coverage reporting

**Files:**
- Create `/Users/tony/Dropbox/Projects/sms-survey/tests/conftest.py`
- Create `/Users/tony/Dropbox/Projects/sms-survey/pytest.ini`

**Code Structure:**
```python
# tests/conftest.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.database import Base
from app.models.session import SurveySession
from app.models.response import SurveyResponse
from app.models.optout import OptOut

@pytest.fixture(scope="session")
def test_engine():
    """Create test database engine"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine

@pytest.fixture
def db_session(test_engine):
    """Create test database session"""
    Session = sessionmaker(bind=test_engine)
    session = Session()
    yield session
    session.rollback()
    session.close()

@pytest.fixture
def sample_survey_session(db_session):
    """Create sample survey session"""
    from app.services.phone_hasher import PhoneHasher

    # Hash a test phone number
    phone_hash = PhoneHasher.hash_phone("+15551234567")

    session = SurveySession(
        phone_hash=phone_hash,
        survey_id="test-survey",
        survey_version="test",
        current_step="q_name",
        consent_given=True,
        context={}
    )
    db_session.add(session)
    db_session.commit()
    return session
```

**Dependencies:** Tasks 1.1-1.4

**Testing:**
```bash
poetry run pytest tests/ -v
```

---

#### Task 7.2: Write Unit Tests for Survey Loader
**Details:**
- Test YAML loading and validation
- Test error handling for invalid YAML
- Test step retrieval
- Test survey caching

**Files:**
- Create `/Users/tony/Dropbox/Projects/sms-survey/tests/unit/test_survey_loader.py`

**Test Cases:**
1. Load valid survey
2. Reject invalid YAML syntax
3. Reject survey with missing required fields
4. Reject survey with invalid step references
5. Cache loaded surveys

**Dependencies:** Task 2.2

**Testing:**
```bash
poetry run pytest tests/unit/test_survey_loader.py -v
```

---

#### Task 7.3: Write Unit Tests for Validation Service
**Details:**
- Test regex validation
- Test choice validation
- Test length constraints
- Test error message generation

**Files:**
- Create `/Users/tony/Dropbox/Projects/sms-survey/tests/unit/test_validation.py`

**Test Cases:**
1. Valid regex match
2. Invalid regex match returns error
3. Valid choice selection
4. Invalid choice returns error
5. Min/max length validation
6. Input normalization (whitespace trimming)

**Dependencies:** Task 2.3

**Testing:**
```bash
poetry run pytest tests/unit/test_validation.py -v
```

---

#### Task 7.4: Write Unit Tests for Survey Engine
**Details:**
- Test consent workflow
- Test step progression
- Test retry logic
- Test conditional branching
- Test context updates
- Test terminal step handling

**Files:**
- Create `/Users/tony/Dropbox/Projects/sms-survey/tests/unit/test_survey_engine.py`

**Test Cases:**
1. New session starts with consent request
2. Valid consent acceptance starts survey
3. Consent decline ends survey
4. Invalid input increments retry counter
5. Max retries triggers error message
6. Valid input progresses to next step
7. Conditional branching selects correct path
8. Terminal step completes survey
9. Context variables updated correctly

**Dependencies:** Task 3.3

**Testing:**
```bash
poetry run pytest tests/unit/test_survey_engine.py -v
```

---

#### Task 7.5: Write Integration Tests for Webhook Flow
**Details:**
- Test complete SMS flow end-to-end
- Test opt-out handling
- Test concurrent requests (locking)
- Test Twilio signature verification

**Files:**
- Create `/Users/tony/Dropbox/Projects/sms-survey/tests/integration/test_webhook_flow.py`

**Test Cases:**
1. New user receives consent message
2. User accepts consent and receives first question
3. User provides valid answer and receives next question
4. User provides invalid answer and receives error message
5. User completes entire survey
6. User sends STOP and gets opted out
7. Opted-out user receives no response
8. Invalid Twilio signature rejected

**Dependencies:** Task 5.2

**Testing:**
```bash
poetry run pytest tests/integration/test_webhook_flow.py -v
```

---

#### Task 7.6: Write Database Locking Tests
**Details:**
- Test pessimistic locking prevents race conditions
- Simulate concurrent requests to same session
- Verify only one request processes at a time

**Files:**
- Create `/Users/tony/Dropbox/Projects/sms-survey/tests/integration/test_database.py`

**Test Cases:**
1. Concurrent requests to same session serialize correctly
2. SELECT FOR UPDATE blocks second transaction
3. No duplicate responses created

**Dependencies:** Task 5.2

**Testing:**
```bash
poetry run pytest tests/integration/test_database.py -v
```

---

### Phase 8: Documentation & Polish (Day 5)

#### Task 8.1: Create Main README
**Details:**
- Project overview and architecture
- Quick start guide
- Development setup instructions
- Deployment guide
- Contributing guidelines

**Files:**
- Create `/Users/tony/Dropbox/Projects/sms-survey/README.md`

**Content Outline:**
1. Project Overview
2. Architecture Diagram
3. Features
4. Quick Start
5. Development Setup
6. Running Tests
7. Deployment
8. Creating Surveys
9. Troubleshooting
10. License

**Dependencies:** All previous tasks

**Testing:** Manual review

---

#### Task 8.2: Add Code Comments and Docstrings
**Details:**
- Add docstrings to all public functions and classes
- Add inline comments for complex logic
- Ensure consistency with Google or NumPy docstring style

**Files:**
- Update all Python files in `app/`

**Dependencies:** All implementation tasks

**Testing:** Manual review and linting

---

#### Task 8.3: Create .gitignore File
**Details:**
- Ignore Python cache files
- Ignore environment files
- Ignore IDE configurations
- Ignore database files

**Files:**
- Create `/Users/tony/Dropbox/Projects/sms-survey/.gitignore`

**Code Structure:**
```
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
.venv/

# Environment
.env
.env.local

# IDEs
.vscode/
.idea/
*.swp
*.swo

# Database
*.db
*.sqlite

# Testing
.coverage
htmlcov/
.pytest_cache/

# Logs
*.log

# OS
.DS_Store
Thumbs.db
```

**Dependencies:** None

**Testing:** Verify files are ignored by git

---

#### Task 8.4: Setup Pre-commit Hooks
**Details:**
- Install pre-commit framework
- Configure black for code formatting
- Configure flake8 for linting
- Configure mypy for type checking

**Files:**
- Create `/Users/tony/Dropbox/Projects/sms-survey/.pre-commit-config.yaml`

**Dependencies:** Task 0.1

**Testing:**
```bash
poetry add --dev pre-commit black flake8 mypy
pre-commit install
pre-commit run --all-files
```

---

### Phase 9: Production Readiness (Day 5)

#### Task 9.1: Add Monitoring and Logging
**Details:**
- Structure logs as JSON for production
- Add request ID tracking
- Log all SMS interactions
- Add error alerting hooks

**Files:**
- Update `/Users/tony/Dropbox/Projects/sms-survey/app/main.py`
- Update `/Users/tony/Dropbox/Projects/sms-survey/app/routes/webhook.py`

**Dependencies:** Task 5.3

**Testing:** Verify log output format

---

#### Task 9.2: Implement Session Cleanup Job
**Details:**
- Create background job to clean up stale sessions
- Delete sessions older than timeout_hours
- Archive completed sessions if needed

**Files:**
- Create `/Users/tony/Dropbox/Projects/sms-survey/app/jobs/cleanup.py`

**Code Structure:**
```python
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.session import SurveySession
from app.services.survey_loader import get_survey_loader

def cleanup_stale_sessions(db: Session):
    """Delete sessions that have been inactive for timeout_hours"""
    loader = get_survey_loader()

    for survey_id in loader.list_surveys():
        survey = loader.load_survey(survey_id)
        timeout_hours = survey.settings.timeout_hours

        cutoff_time = datetime.utcnow() - timedelta(hours=timeout_hours)

        stale_sessions = db.query(SurveySession).filter(
            SurveySession.survey_id == survey_id,
            SurveySession.updated_at < cutoff_time,
            SurveySession.completed_at == None
        ).all()

        for session in stale_sessions:
            db.delete(session)

        db.commit()
```

**Dependencies:** Tasks 1.2, 2.2

**Testing:** Unit test with mock sessions

---

#### Task 9.3: Add Rate Limiting
**Details:**
- Implement rate limiting per phone number
- Prevent abuse/spam
- Return appropriate error messages

**Files:**
- Create `/Users/tony/Dropbox/Projects/sms-survey/app/middleware/rate_limit.py`

**Dependencies:** Task 5.2

**Testing:** Integration test with rapid requests

---

#### Task 9.4: Security Hardening Review
**Details:**
- Review SQL injection prevention (use parameterized queries)
- Verify Twilio signature verification is enforced
- Ensure no secrets in logs
- Add security headers to responses
- Review YAML parsing for code injection

**Files:**
- Review all files in `app/`

**Dependencies:** All implementation tasks

**Testing:** Security audit checklist

---

#### Task 9.5: Performance Testing
**Details:**
- Load test webhook endpoint
- Measure database query performance
- Verify pessimistic locking doesn't cause bottlenecks
- Test scale-to-zero startup time

**Files:**
- Create `/Users/tony/Dropbox/Projects/sms-survey/tests/performance/test_load.py`

**Dependencies:** Task 5.2

**Testing:**
```bash
# Use locust or ab for load testing
ab -n 1000 -c 10 http://localhost:8000/health
```

---

## Testing Strategy Summary

### Unit Tests
- **Target:** Individual functions and classes in isolation
- **Coverage:** Survey loader, validation, branching, template rendering
- **Framework:** pytest with mocks

### Integration Tests
- **Target:** Complete flows with database
- **Coverage:** Webhook endpoint, survey engine with database, opt-out handling
- **Framework:** pytest with test database

### End-to-End Tests
- **Target:** Complete user journey from first SMS to survey completion
- **Coverage:** Full survey flow, error handling, conditional branching
- **Framework:** pytest with FastAPI TestClient

### Performance Tests
- **Target:** System under load
- **Coverage:** Concurrent requests, database locking, response times
- **Framework:** locust or Apache Bench

### Test Execution Commands
```bash
# All tests
poetry run pytest tests/ -v --cov=app --cov-report=html

# Unit tests only
poetry run pytest tests/unit/ -v

# Integration tests only
poetry run pytest tests/integration/ -v

# With coverage report
poetry run pytest tests/ --cov=app --cov-report=term-missing
```

---

## Risk Assessment

### Risk 0: Phone Number Privacy Breach
**Impact:** High - Exposure of supporter phone numbers could harm advocacy work

**Mitigation:**
- Phone numbers hashed with SHA-256 + application salt immediately upon receipt
- Database stores only non-reversible hashes (64-char hex strings)
- Logs truncate hashes to first 12 characters
- `PHONE_HASH_SALT` kept secret and never committed to git
- Testing: Unit tests verify hashing is deterministic and non-reversible (Task 0.6)

**Note:** This enables the privacy commitment "We don't store your phone number."

### Risk 1: Race Conditions (Double Texting)
**Impact:** High - Could lead to duplicate responses or skipped steps

**Mitigation:**
- Implemented pessimistic locking with `SELECT FOR UPDATE`
- Transaction isolation at READ COMMITTED level
- Testing: Concurrent request simulation tests (Task 7.6)

### Risk 2: Twilio Webhook Replay Attacks
**Impact:** Medium - Malicious actors could replay valid requests

**Mitigation:**
- Twilio signature verification enforced on all webhooks
- Message SID logging for deduplication detection
- HTTPS-only communication
- Testing: Invalid signature rejection tests (Task 7.5)

### Risk 3: Survey YAML Misconfiguration
**Impact:** Medium - Broken surveys could prevent user progress

**Mitigation:**
- Strict Pydantic validation on load
- Required step reference validation
- Example survey with documentation
- Non-technical staff testing before deployment
- Testing: YAML validation tests (Task 7.2)

### Risk 4: Database Connection Pool Exhaustion
**Impact:** Medium - Could cause webhook timeouts

**Mitigation:**
- Connection pooling with reasonable limits (5 base, 10 overflow)
- Connection pre-ping to detect stale connections
- Scale-to-zero with fast startup
- Monitoring database connection metrics
- Testing: Load testing (Task 9.5)

### Risk 5: Unbounded Survey Costs
**Impact:** High - SMS costs could escalate with loops or spam

**Mitigation:**
- STOP handler at gateway level
- Max retry limits per step (3 attempts)
- Session timeout for inactive surveys (48 hours)
- Rate limiting per phone number
- Testing: Opt-out and retry limit tests (Task 7.5)

### Risk 6: Jinja2 Template Injection
**Impact:** Low - Malicious context variables could break rendering

**Mitigation:**
- Jinja2 autoescape enabled
- StrictUndefined mode to catch missing variables
- Input validation before storing in context
- No user input directly in template definitions
- Testing: Template rendering tests (Task 3.1)

### Risk 7: Alembic Migration Failures on Deploy
**Impact:** High - Could break production deployment

**Mitigation:**
- Migration testing in staging environment
- Fly.io release_command runs migrations before app starts
- Manual migration review before production
- Rollback procedures documented
- Testing: Migration up/down tests (Task 1.6)

---

## Success Criteria Checklist

### Functional Requirements
- [ ] Survey definitions load from YAML files
- [ ] Consent workflow implemented (accept/decline)
- [ ] All question types supported (text, regex, choice, terminal)
- [ ] Input validation with custom error messages
- [ ] Retry logic (max 3 attempts per step)
- [ ] Conditional branching based on context
- [ ] Jinja2 template variables work in questions
- [ ] STOP keyword opts users out
- [ ] Survey completion tracked in database
- [ ] TwiML responses generated correctly

### Technical Requirements
- [ ] FastAPI application runs on Fly.io
- [ ] PostgreSQL database with Alembic migrations
- [ ] Pessimistic locking prevents race conditions
- [ ] Twilio signature verification enforced
- [ ] Git commit SHA tracked for survey versioning
- [ ] Scale-to-zero configuration working
- [ ] Health check endpoint operational
- [ ] Session cleanup job implemented
- [ ] Phone number hashing service implemented
- [ ] Database stores only phone hashes (no plaintext)
- [ ] Logs truncate hashes (never show full hash or plaintext)

### Quality Requirements
- [ ] Unit test coverage > 80%
- [ ] Integration tests for critical paths
- [ ] Load testing shows acceptable performance
- [ ] Code linted and formatted consistently
- [ ] All docstrings present
- [ ] README documentation complete
- [ ] Survey YAML format documented
- [ ] Deployment guide written

### Deployment Requirements
- [ ] Dockerfile builds successfully
- [ ] fly.toml configured correctly
- [ ] Environment variables documented
- [ ] Migrations run on deployment
- [ ] Twilio webhook URL configured
- [ ] Monitoring and logging operational
- [ ] Rollback procedure tested

---

## Estimated Timeline

### Day 1: Infrastructure & Database (8 hours)
- **Phase 0:** Project Setup (2 hours)
- **Phase 1:** Database Layer (6 hours)

**Deliverables:** Working database models, Alembic migrations, Python environment

---

### Day 2: Survey Engine Core (8 hours)
- **Phase 2:** Survey Definition & Loading (4 hours)
- **Phase 3:** Survey Engine Logic (4 hours)

**Deliverables:** YAML loader, validation service, survey engine state machine

---

### Day 3: Integration & API (8 hours)
- **Phase 4:** Twilio Integration (3 hours)
- **Phase 5:** FastAPI Routes (5 hours)

**Deliverables:** Working webhook endpoint, TwiML generation, signature verification

---

### Day 4: Deployment & Testing (8 hours)
- **Phase 6:** Deployment Configuration (3 hours)
- **Phase 7:** Testing Strategy (5 hours)

**Deliverables:** Dockerfile, Fly.io config, comprehensive test suite

---

### Day 5: Polish & Production Readiness (8 hours)
- **Phase 8:** Documentation (3 hours)
- **Phase 9:** Production Readiness (5 hours)

**Deliverables:** Complete documentation, monitoring, security hardening, performance testing

---

**Total Estimated Time:** 5 days (40 hours)

**Note:** Timeline assumes full-time focused development with AI assistance (Copilot/Claude). Buffer time included for debugging and integration issues.

---

## Dependencies Graph

```
Phase 0 (Setup)
    ├─> Phase 1 (Database)
    ├─> Phase 2 (Survey Loading)
    └─> Phase 6 (Deployment)

Phase 1 (Database)
    └─> Phase 5 (FastAPI Routes)

Phase 2 (Survey Loading)
    └─> Phase 3 (Survey Engine)

Phase 3 (Survey Engine)
    └─> Phase 5 (FastAPI Routes)

Phase 4 (Twilio)
    └─> Phase 5 (FastAPI Routes)

Phase 5 (FastAPI Routes)
    ├─> Phase 7 (Testing)
    └─> Phase 9 (Production)

Phase 6 (Deployment)
    └─> Phase 9 (Production)

Phase 7 (Testing)
    └─> Phase 9 (Production)

Phase 8 (Documentation) [Parallel to other phases]
```

---

## Next Steps

After completing this implementation plan:

1. **Review with stakeholders** to ensure requirements alignment
2. **Setup development environment** following Task 0.1-0.5
3. **Create Git branch** for development
4. **Begin Phase 1 implementation** with database setup
5. **Iterate through phases sequentially** with testing at each step
6. **Deploy to Fly.io staging** after Phase 6
7. **Conduct end-to-end testing** with real Twilio numbers
8. **Create first production survey** using documented YAML format
9. **Deploy to production** with monitoring enabled
10. **Train non-technical staff** on survey creation

---

## Appendix: Key Design Decisions

### Why Hash Phone Numbers Instead of Storing Plaintext?
Phone numbers are sensitive PII, especially for advocacy/political work. By using SHA-256 one-way hashing with an application salt:
- **Privacy:** We can truthfully say "We don't store your phone number"
- **Breach Protection:** Stolen database doesn't expose phone numbers
- **Functionality Preserved:** Deterministic hashing allows session lookups
- **Compliance:** Better GDPR/privacy posture
- **Trust:** Demonstrates respect for supporter privacy

The limited keyspace of phone numbers means hashes could theoretically be brute-forced, but a strong secret salt makes this impractical. Twilio still has plaintext numbers (required for SMS delivery), but we control our database privacy.

### Why Pessimistic Locking?
Optimistic locking requires retry logic at the application level, increasing complexity. Pessimistic locking (`SELECT FOR UPDATE`) provides simpler guarantees for webhook processing where conflicts are rare but consequences are high.

### Why YAML over JSON?
YAML is more human-readable for non-technical staff and supports multi-line strings natively, making survey text easier to edit.

### Why FastAPI over Flask?
FastAPI provides automatic API documentation, Pydantic integration, and native async support, making it ideal for webhook processing.

### Why SQLAlchemy Core + ORM Hybrid?
ORM for model definition and relationships, with raw SQL available for complex queries like locking. Best of both worlds.

### Why Fly.io over AWS Lambda?
Fly.io provides simpler PostgreSQL integration, better cold-start times, and easier deployment for this use case. Scale-to-zero provides similar cost benefits.

### Why No Session Persistence Layer (Redis)?
Survey sessions are infrequent enough that PostgreSQL provides adequate performance. Adding Redis would increase operational complexity without significant benefit.

---

**End of Implementation Plan**
