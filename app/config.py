"""Application configuration management using Pydantic Settings.

This module loads and validates environment variables using Pydantic Settings.
All configuration is loaded from environment variables or a .env file.
"""

from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Attributes:
        database_url: PostgreSQL connection string
        database_pool_size: Number of connections to maintain in pool
        database_max_overflow: Maximum overflow connections beyond pool_size
        twilio_account_sid: Twilio account SID
        twilio_auth_token: Twilio authentication token
        twilio_phone_number: Twilio phone number in E.164 format
        environment: Application environment (development, staging, production)
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        surveys_dir: Path to directory containing survey YAML files
        git_commit_sha: Git commit SHA for survey versioning
        secret_key: Secret key for cryptographic operations
        phone_hash_salt: Salt for one-way phone number hashing
        allowed_origins: List of allowed CORS origins
    """

    # Database Configuration
    database_url: str = Field(
        description="PostgreSQL connection string"
    )
    database_pool_size: int = Field(
        default=5,
        description="Number of database connections in pool"
    )
    database_max_overflow: int = Field(
        default=10,
        description="Maximum overflow connections beyond pool size"
    )

    # Twilio Configuration
    twilio_account_sid: str = Field(
        description="Twilio account SID"
    )
    twilio_auth_token: str = Field(
        description="Twilio authentication token"
    )
    twilio_phone_number: str = Field(
        description="Twilio phone number in E.164 format"
    )

    # Application Configuration
    environment: str = Field(
        default="development",
        description="Application environment"
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level"
    )
    surveys_dir: str = Field(
        default="./surveys",
        description="Path to surveys directory"
    )
    git_commit_sha: str = Field(
        default="local",
        description="Git commit SHA for versioning"
    )

    # Security Configuration
    secret_key: str = Field(
        description="Secret key for cryptographic operations"
    )
    phone_hash_salt: str = Field(
        description="Salt for one-way phone number hashing (must be kept secret)"
    )
    allowed_origins: str = Field(
        default="http://localhost:3000,http://localhost:8000",
        description="Comma-separated list of allowed CORS origins"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate environment is one of the allowed values."""
        allowed = {"development", "staging", "production"}
        if v.lower() not in allowed:
            raise ValueError(f"Environment must be one of {allowed}")
        return v.lower()

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is one of the allowed values."""
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in allowed:
            raise ValueError(f"Log level must be one of {allowed}")
        return v_upper

    @field_validator("twilio_phone_number")
    @classmethod
    def validate_phone_number(cls, v: str) -> str:
        """Validate phone number is in E.164 format."""
        if not v.startswith("+"):
            raise ValueError("Phone number must be in E.164 format (e.g., +15551234567)")
        return v

    def get_allowed_origins_list(self) -> List[str]:
        """Parse allowed_origins string into a list."""
        return [origin.strip() for origin in self.allowed_origins.split(",")]

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment == "development"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance.

    Returns:
        Settings: Application settings singleton

    Note:
        Uses lru_cache to ensure settings are only loaded once
        and shared across the application.
    """
    return Settings()
