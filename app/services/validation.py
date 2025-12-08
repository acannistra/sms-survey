"""Input validation service for survey responses.

This module validates user input against survey step validation rules,
normalizes values, and generates appropriate error messages.
"""

import re
from typing import Optional
from dataclasses import dataclass

from app.schemas.survey import SurveyStep, QuestionType
from app.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class ValidationResult:
    """Result of input validation.

    Attributes:
        is_valid: Whether input passed validation
        normalized_value: Cleaned/normalized input value
        error_message: Error message if validation failed
    """
    is_valid: bool
    normalized_value: Optional[str]
    error_message: Optional[str]


class InputValidator:
    """Service for validating user input against survey step rules."""

    @staticmethod
    def validate(step: SurveyStep, user_input: str) -> ValidationResult:
        """Validate user input against step validation rules.

        Handles validation for all question types:
        - text: min_length, max_length
        - regex: pattern matching
        - choice: exact match (case-insensitive)
        - terminal: always valid

        Args:
            step: Survey step with validation rules
            user_input: Raw user input from SMS

        Returns:
            ValidationResult with validation status and normalized value

        Example:
            >>> step = SurveyStep(id="ask_zip", type="regex", validation=ValidationRules(pattern=r'^\d{5}$'))
            >>> result = InputValidator.validate(step, "12345")
            >>> print(result.is_valid)
            True
        """
        # Normalize input (strip whitespace)
        normalized = user_input.strip()

        # Terminal steps are always valid
        if step.type == QuestionType.TERMINAL:
            return ValidationResult(
                is_valid=True,
                normalized_value=normalized,
                error_message=None
            )

        # Route to type-specific validator
        if step.type == QuestionType.TEXT:
            return InputValidator._validate_text(step, normalized)
        elif step.type == QuestionType.REGEX:
            return InputValidator._validate_regex(step, normalized)
        elif step.type == QuestionType.CHOICE:
            return InputValidator._validate_choice(step, normalized)
        else:
            # Should never happen due to Pydantic validation
            logger.error(f"Unknown question type: {step.type}")
            return ValidationResult(
                is_valid=False,
                normalized_value=None,
                error_message="Internal error: invalid question type"
            )

    @staticmethod
    def _validate_text(step: SurveyStep, normalized: str) -> ValidationResult:
        """Validate text input against min/max length rules.

        Args:
            step: Survey step with text validation rules
            normalized: Normalized user input

        Returns:
            ValidationResult
        """
        if step.validation is None:
            # No validation rules, accept any non-empty input
            if len(normalized) > 0:
                return ValidationResult(
                    is_valid=True,
                    normalized_value=normalized,
                    error_message=None
                )
            else:
                return ValidationResult(
                    is_valid=False,
                    normalized_value=None,
                    error_message=step.error_message or "Please enter a response."
                )

        # Check min_length
        if step.validation.min_length is not None:
            if len(normalized) < step.validation.min_length:
                error = step.error_message or f"Please enter at least {step.validation.min_length} characters."
                return ValidationResult(
                    is_valid=False,
                    normalized_value=None,
                    error_message=error
                )

        # Check max_length
        if step.validation.max_length is not None:
            if len(normalized) > step.validation.max_length:
                error = step.error_message or f"Please enter no more than {step.validation.max_length} characters."
                return ValidationResult(
                    is_valid=False,
                    normalized_value=None,
                    error_message=error
                )

        return ValidationResult(
            is_valid=True,
            normalized_value=normalized,
            error_message=None
        )

    @staticmethod
    def _validate_regex(step: SurveyStep, normalized: str) -> ValidationResult:
        """Validate input against regex pattern.

        Args:
            step: Survey step with regex pattern
            normalized: Normalized user input

        Returns:
            ValidationResult
        """
        if step.validation is None or step.validation.pattern is None:
            # Should not happen due to schema validation
            logger.error(f"Regex step {step.id} missing pattern")
            return ValidationResult(
                is_valid=False,
                normalized_value=None,
                error_message="Internal error: missing validation pattern"
            )

        try:
            pattern = re.compile(step.validation.pattern)
            if pattern.match(normalized):
                return ValidationResult(
                    is_valid=True,
                    normalized_value=normalized,
                    error_message=None
                )
            else:
                error = step.error_message or "Invalid format. Please try again."
                return ValidationResult(
                    is_valid=False,
                    normalized_value=None,
                    error_message=error
                )
        except re.error as e:
            logger.error(f"Invalid regex pattern in step {step.id}: {e}")
            return ValidationResult(
                is_valid=False,
                normalized_value=None,
                error_message="Internal error: invalid validation pattern"
            )

    @staticmethod
    def _validate_choice(step: SurveyStep, normalized: str) -> ValidationResult:
        """Validate choice input against available options.

        Matches are case-insensitive. Returns the 'value' field of the
        matched choice for storage in context.

        Args:
            step: Survey step with choice options
            normalized: Normalized user input

        Returns:
            ValidationResult with choice value if valid
        """
        if step.validation is None or step.validation.choices is None:
            # Should not happen due to schema validation
            logger.error(f"Choice step {step.id} missing choices")
            return ValidationResult(
                is_valid=False,
                normalized_value=None,
                error_message="Internal error: missing choice options"
            )

        # Case-insensitive matching against display values
        normalized_lower = normalized.lower()
        for choice in step.validation.choices:
            if choice.display.lower() == normalized_lower:
                # Return the value field for storage
                return ValidationResult(
                    is_valid=True,
                    normalized_value=choice.value,
                    error_message=None
                )

        # No match found
        valid_options = [choice.display for choice in step.validation.choices]
        error = step.error_message or f"Please reply with one of: {', '.join(valid_options)}"
        return ValidationResult(
            is_valid=False,
            normalized_value=None,
            error_message=error
        )
