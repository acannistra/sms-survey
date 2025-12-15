"""Health check endpoint for monitoring and deployment verification.

This module provides a health check endpoint that verifies the application
is running and can connect to the database.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get("/health")
async def health_check(db: Session = Depends(get_db)) -> dict:
    """Health check endpoint.

    Verifies that:
    1. The application is running
    2. Database connection is working

    Returns:
        dict: Health check status with database connection info

    Raises:
        HTTPException: If database connection fails (503 Service Unavailable)

    Example response:
        {
            "status": "healthy",
            "database": "connected"
        }
    """
    try:
        # Test database connection with simple query
        db.execute(text("SELECT 1"))

        logger.debug("Health check passed")

        return {
            "status": "healthy",
            "database": "connected"
        }

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail="Service unavailable - database connection failed"
        )
