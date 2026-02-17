"""Unit tests for health check endpoint.

Tests the health check endpoint for monitoring and deployment verification.
"""

import pytest
from unittest.mock import Mock
from fastapi import HTTPException

from app.routes.health import health_check


@pytest.mark.unit
class TestHealthEndpoint:
    """Test suite for health check endpoint."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, db_session):
        """Test health check returns success when database is accessible."""
        result = await health_check(db_session)

        assert result["status"] == "healthy"
        assert result["database"] == "connected"

    @pytest.mark.asyncio
    async def test_health_check_database_failure(self, db_session):
        """Test health check returns 503 when database is unavailable."""
        # Mock database to raise exception
        db_session.execute = Mock(side_effect=Exception("Connection failed"))

        with pytest.raises(HTTPException) as exc_info:
            await health_check(db_session)

        assert exc_info.value.status_code == 503
        assert "database connection failed" in exc_info.value.detail.lower()
