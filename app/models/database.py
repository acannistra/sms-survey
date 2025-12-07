"""Database setup and session management using SQLAlchemy 2.0.

This module configures the database engine, session factory, and base class
for all ORM models using modern SQLAlchemy 2.0 patterns.
"""

from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Base class for all ORM models.

    Uses SQLAlchemy 2.0's DeclarativeBase for modern type-safe models.
    All models should inherit from this class.
    """
    pass


# Get database URL from settings
settings = get_settings()

# Create engine with connection pooling
# SQLite doesn't support pool_size/max_overflow, so use them conditionally
engine_kwargs = {
    "pool_pre_ping": True,  # Verify connections before using
    "echo": settings.is_development,  # Log SQL in development
}

# Add pooling parameters only for PostgreSQL
if not settings.database_url.startswith("sqlite"):
    engine_kwargs["pool_size"] = settings.database_pool_size
    engine_kwargs["max_overflow"] = settings.database_max_overflow

engine = create_engine(settings.database_url, **engine_kwargs)

# Create session factory
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,  # Prevent lazy loading after commit
)


def get_db() -> Generator[Session, None, None]:
    """Dependency function for FastAPI to provide database sessions.

    Yields:
        Session: SQLAlchemy database session

    Example:
        @app.get("/example")
        def example_route(db: Session = Depends(get_db)):
            # Use db session here
            pass

    Note:
        The session is automatically closed after the request completes,
        even if an exception occurs.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
