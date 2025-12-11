"""FastAPI application entry point for SMS Survey Engine.

This module initializes the FastAPI application, sets up logging,
registers routers, and handles global exception handling.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.logging_config import setup_logging, get_logger
from app.routes import health, webhook

# Initialize logger (will be configured during startup)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager.

    Handles startup and shutdown events for the application.

    Startup:
    - Configure logging
    - Log application startup information

    Shutdown:
    - Log shutdown event
    - Clean up resources (if needed)

    Args:
        app: FastAPI application instance

    Yields:
        None
    """
    # Startup
    settings = get_settings()
    setup_logging()

    logger.info(
        f"SMS Survey Engine starting - "
        f"Environment: {settings.environment}, "
        f"Log Level: {settings.log_level}, "
        f"Database: {settings.database_url.split('@')[-1] if '@' in settings.database_url else 'configured'}, "
        f"Version: {settings.git_commit_sha}"
    )

    yield

    # Shutdown
    logger.info("SMS Survey Engine shutting down")


# Initialize FastAPI application
app = FastAPI(
    title="SMS Survey Engine",
    description="A privacy-first SMS survey engine using Twilio webhooks and PostgreSQL",
    version="1.0.0",
    lifespan=lifespan
)


# Root endpoint
@app.get("/")
async def root() -> dict:
    """Root endpoint with basic API information.

    Returns:
        dict: API information and status
    """
    settings = get_settings()
    return {
        "service": "SMS Survey Engine",
        "version": "1.0.0",
        "environment": settings.environment,
        "status": "operational"
    }


# Register routers
app.include_router(health.router, tags=["Health"])
app.include_router(webhook.router, tags=["Webhook"])


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Global exception handler for unhandled exceptions.

    Logs all unhandled exceptions and returns a generic error response
    to prevent leaking sensitive information.

    Args:
        request: FastAPI request object
        exc: Exception that was raised

    Returns:
        JSONResponse: Generic error response
    """
    logger.error(
        f"Unhandled exception for {request.method} {request.url}: {exc}",
        exc_info=True
    )

    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": "An unexpected error occurred. Please try again later."
        }
    )
