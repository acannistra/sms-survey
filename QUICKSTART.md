# Quick Start Guide

## Initial Setup (One-time)

```bash
# Activate virtual environment
source .venv/bin/activate

# Copy environment template
cp .env.example .env

# Edit .env with your actual credentials
nano .env  # or use your preferred editor
```

## Common Commands

### Virtual Environment

```bash
# Activate
source .venv/bin/activate

# Deactivate
deactivate
```

### Dependency Management

```bash
# Install all dependencies (including dev)
uv pip install -e ".[dev]"

# Install only production dependencies
uv pip install -e .

# Add a new dependency (edit pyproject.toml, then reinstall)
uv pip install -e ".[dev]"
```

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/unit/test_config.py

# Run with verbose output
pytest -v

# Run Phase 0 verification
python test_phase0.py
```

### Database (Coming in Phase 1)

```bash
# Create a new migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Show current migration
alembic current

# Show migration history
alembic history
```

### Running the Application (Coming in Phase 5)

```bash
# Development server with auto-reload
uvicorn app.main:app --reload

# Production server
uvicorn app.main:app --host 0.0.0.0 --port 8000

# With custom log level
LOG_LEVEL=DEBUG uvicorn app.main:app --reload
```

### Code Quality (Coming in Phase 8)

```bash
# Format code with black
black app/ tests/

# Lint with flake8
flake8 app/ tests/

# Type check with mypy
mypy app/

# Run pre-commit hooks
pre-commit run --all-files
```

## Project Structure

```
sms-survey/
├── app/                    # Application code
│   ├── config.py          # Configuration management
│   ├── logging_config.py  # Logging setup
│   ├── main.py           # FastAPI app (Phase 5)
│   ├── models/           # Database models (Phase 1)
│   ├── schemas/          # Pydantic schemas (Phase 2)
│   ├── services/         # Business logic (Phase 2-3)
│   ├── routes/           # API endpoints (Phase 5)
│   └── middleware/       # Middleware (Phase 4)
├── alembic/              # Database migrations (Phase 1)
├── surveys/              # Survey YAML files (Phase 2)
├── tests/                # Test files (Phase 7)
├── .env                  # Environment variables (not in git)
├── .env.example         # Environment template
└── pyproject.toml       # Dependencies

```

## Environment Variables

Required variables (see `.env.example` for details):

- `DATABASE_URL` - PostgreSQL connection string
- `TWILIO_ACCOUNT_SID` - Twilio account SID
- `TWILIO_AUTH_TOKEN` - Twilio auth token
- `TWILIO_PHONE_NUMBER` - Your Twilio phone number
- `SECRET_KEY` - Application secret key

Optional variables:

- `ENVIRONMENT` - development/staging/production (default: development)
- `LOG_LEVEL` - DEBUG/INFO/WARNING/ERROR (default: INFO)
- `SURVEYS_DIR` - Path to surveys directory (default: ./surveys)

## Testing Configuration

To test configuration loading:

```python
import os

# Set test environment variables
os.environ['DATABASE_URL'] = 'postgresql://test:test@localhost/test'
os.environ['TWILIO_ACCOUNT_SID'] = 'ACtest'
os.environ['TWILIO_AUTH_TOKEN'] = 'test_token'
os.environ['TWILIO_PHONE_NUMBER'] = '+15551234567'
os.environ['SECRET_KEY'] = 'test_secret'

from app.config import get_settings
settings = get_settings()
print(f"Environment: {settings.environment}")
```

## Logging Example

```python
import os

# Set required env vars (as above)
from app.logging_config import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)

logger.info("Application started")
logger.warning("Warning message")
logger.error("Error occurred", extra={"user_id": 123})
```

## Next Steps

Phase 0 is complete. Next phases:

1. **Phase 1** - Database Layer (models, migrations)
2. **Phase 2** - Survey Definition & Loading (YAML schemas)
3. **Phase 3** - Survey Engine Core Logic (state machine)
4. **Phase 4** - Twilio Integration (webhooks, TwiML)
5. **Phase 5** - FastAPI Routes & Application (API endpoints)

## Troubleshooting

### Import Errors

If you get import errors, make sure:
1. Virtual environment is activated: `source .venv/bin/activate`
2. Package is installed in editable mode: `uv pip install -e ".[dev]"`

### Environment Variable Errors

If you get validation errors:
1. Copy `.env.example` to `.env`
2. Fill in all required variables
3. Check phone number format (must start with +)

### Database Connection Issues (Phase 1+)

1. Verify PostgreSQL is running
2. Check DATABASE_URL format: `postgresql://user:pass@host:port/database`
3. Test connection: `psql $DATABASE_URL -c "SELECT 1"`

## Getting Help

- See `README.md` for project overview
- See `plans/implementation-plan.md` for detailed implementation guide
- See `surveys/README.md` for survey YAML format documentation
- See `PHASE0_COMPLETION.md` for Phase 0 completion details
