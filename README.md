# SMS Survey Engine

A lightweight, serverless SMS survey engine that processes incoming text messages via Twilio webhooks, maintains survey state in PostgreSQL, and dynamically loads survey definitions from git-versioned YAML files.

## Features

- **Twilio Integration**: Webhook-based SMS processing with signature verification
- **PostgreSQL Database**: Survey sessions and responses stored with SQLAlchemy ORM
- **YAML Survey Definitions**: Non-technical staff can edit surveys in version-controlled YAML files
- **Jinja2 Templating**: Dynamic question text based on previous responses
- **Conditional Branching**: Complex survey logic with conditional next steps
- **Consent Workflow**: Built-in consent management
- **Opt-out Handling**: Automatic STOP/UNSUBSCRIBE detection
- **Scale-to-Zero**: Designed for cost-efficient deployment on Fly.io

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL database
- Twilio account with phone number

### Installation

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"
```

### Configuration

Copy `.env.example` to `.env` and configure your settings:

```bash
cp .env.example .env
# Edit .env with your configuration
```

### Running the Application

```bash
# Run database migrations
alembic upgrade head

# Start the development server
uvicorn app.main:app --reload
```

## Documentation

- [Implementation Plan](plans/implementation-plan.md) - Complete implementation details
- [Survey YAML Format](surveys/README.md) - How to create and edit surveys

## Project Status

This project is currently in development. Phase 0 (Project Setup & Infrastructure) is in progress.

## License

MIT License
