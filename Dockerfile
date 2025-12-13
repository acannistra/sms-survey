# Multi-stage build for SMS Survey Engine
# Stage 1: Builder - Install dependencies and build wheels
FROM python:3.11-slim AS builder

# Install build dependencies for psycopg2-binary and other compiled packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml README.md ./

# Install dependencies into a virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install the package and its dependencies
RUN pip install --no-cache-dir -U pip setuptools wheel && \
    pip install --no-cache-dir -e .

# Stage 2: Runtime - Minimal image with only runtime dependencies
FROM python:3.11-slim

# Install only runtime dependencies (PostgreSQL client library)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r appuser -g 1000 && \
    useradd -r -u 1000 -g appuser -m -s /bin/bash appuser

# Set working directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application code
COPY app/ ./app/
COPY surveys/ ./surveys/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Set ownership to non-root user
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Set environment variables
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').read()" || exit 1

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
