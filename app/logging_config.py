"""Logging configuration for the SMS Survey Engine.

This module sets up structured logging with JSON formatting for production
and human-readable formatting for development. It includes request ID tracking
for debugging and correlation across log entries.
"""

import logging
import sys
from typing import Any, Dict

from app.config import get_settings


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging in production.

    Formats log records as JSON objects with timestamp, level, message,
    and additional context fields.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON string.

        Args:
            record: Log record to format

        Returns:
            JSON-formatted log string
        """
        import json
        from datetime import datetime

        log_data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields from log record
        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id

        if hasattr(record, "phone_number"):
            log_data["phone_number"] = record.phone_number

        if hasattr(record, "survey_id"):
            log_data["survey_id"] = record.survey_id

        if hasattr(record, "session_id"):
            log_data["session_id"] = record.session_id

        # Add any custom extra fields
        for key, value in record.__dict__.items():
            if key not in [
                "name",
                "msg",
                "args",
                "created",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "message",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "thread",
                "threadName",
                "exc_info",
                "exc_text",
                "stack_info",
                "request_id",
                "phone_number",
                "survey_id",
                "session_id",
            ]:
                log_data[key] = value

        return json.dumps(log_data)


class DevelopmentFormatter(logging.Formatter):
    """Human-readable formatter for development.

    Formats log records with color coding and clear structure for
    easier reading during development.
    """

    # ANSI color codes
    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
        "RESET": "\033[0m",  # Reset
    }

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with colors for development.

        Args:
            record: Log record to format

        Returns:
            Colored, formatted log string
        """
        color = self.COLORS.get(record.levelname, self.COLORS["RESET"])
        reset = self.COLORS["RESET"]

        # Format base message
        formatted = (
            f"{color}[{record.levelname:8}]{reset} "
            f"{record.name:30} - {record.getMessage()}"
        )

        # Add request ID if present
        if hasattr(record, "request_id"):
            formatted += f" [request_id={record.request_id}]"

        # Add exception info if present
        if record.exc_info:
            formatted += "\n" + self.formatException(record.exc_info)

        return formatted


def setup_logging() -> None:
    """Configure application logging based on environment.

    In production, uses JSON formatting for structured logs.
    In development, uses colored human-readable formatting.

    The logging configuration includes:
    - Appropriate log level based on settings
    - Request ID tracking capability
    - Structured fields for correlation
    - Console output to stdout
    """
    settings = get_settings()

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(settings.log_level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(settings.log_level)

    # Set formatter based on environment
    if settings.is_production:
        formatter = JSONFormatter()
    else:
        formatter = DevelopmentFormatter()

    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Set log levels for third-party libraries
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("alembic").setLevel(logging.INFO)

    # Log startup message
    logger = logging.getLogger(__name__)
    logger.info(
        f"Logging configured - Environment: {settings.environment}, "
        f"Level: {settings.log_level}"
    )


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for the given name.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


class RequestContextFilter(logging.Filter):
    """Logging filter that adds request context to log records.

    This filter can be used to automatically add request_id and other
    context fields to all log records within a request context.
    """

    def __init__(self, request_id: str = None):
        """Initialize filter with request context.

        Args:
            request_id: Request ID to add to log records
        """
        super().__init__()
        self.request_id = request_id

    def filter(self, record: logging.LogRecord) -> bool:
        """Add context fields to log record.

        Args:
            record: Log record to modify

        Returns:
            Always True to allow the record through
        """
        if self.request_id:
            record.request_id = self.request_id
        return True
