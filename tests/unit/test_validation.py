"""Unit tests for input validation service.

Tests validation logic for all question types.
"""

import pytest

from app.services.validation import InputValidator, ValidationResult
from app.schemas.survey import (
    SurveyStep,
    QuestionType,
    ValidationRules,
    ChoiceOption,
)


class TestInputValidator:
    """Tests for InputValidator class."""

    def test_terminal_step_always_valid(self):
        """Test that terminal steps are always valid."""
        step = SurveyStep(
            id="completion",
            text="Thank you!",
            type=QuestionType.TERMINAL
        )

        result = InputValidator.validate(step, "anything")
        assert result.is_valid
        assert result.normalized_value == "anything"

    def test_text_validation_no_rules(self):
        """Test text validation with no rules (accepts non-empty)."""
        step = SurveyStep(
            id="ask_name",
            text="What's your name?",
            type=QuestionType.TEXT,
            next="completion"
        )

        # Non-empty input valid
        result = InputValidator.validate(step, "Alice")
        assert result.is_valid
        assert result.normalized_value == "Alice"

        # Empty input invalid
        result = InputValidator.validate(step, "  ")
        assert not result.is_valid
        assert "enter a response" in result.error_message.lower()

    def test_text_validation_min_length(self):
        """Test text validation with minimum length."""
        step = SurveyStep(
            id="ask_name",
            text="What's your name?",
            type=QuestionType.TEXT,
            validation=ValidationRules(min_length=3),
            next="completion"
        )

        # Too short
        result = InputValidator.validate(step, "Al")
        assert not result.is_valid
        assert "3 characters" in result.error_message

        # Exactly min length
        result = InputValidator.validate(step, "Bob")
        assert result.is_valid

        # Longer than min
        result = InputValidator.validate(step, "Alice")
        assert result.is_valid

    def test_text_validation_max_length(self):
        """Test text validation with maximum length."""
        step = SurveyStep(
            id="ask_name",
            text="What's your name?",
            type=QuestionType.TEXT,
            validation=ValidationRules(max_length=10),
            next="completion"
        )

        # Too long
        result = InputValidator.validate(step, "VeryLongName123")
        assert not result.is_valid
        assert "10 characters" in result.error_message

        # Exactly max length
        result = InputValidator.validate(step, "TenLetters")
        assert result.is_valid

        # Shorter than max
        result = InputValidator.validate(step, "Alice")
        assert result.is_valid

    def test_text_validation_min_max_length(self):
        """Test text validation with both min and max length."""
        step = SurveyStep(
            id="ask_name",
            text="What's your name?",
            type=QuestionType.TEXT,
            validation=ValidationRules(min_length=2, max_length=50),
            next="completion"
        )

        # Too short
        result = InputValidator.validate(step, "A")
        assert not result.is_valid

        # Within range
        result = InputValidator.validate(step, "Alice")
        assert result.is_valid

        # Too long
        result = InputValidator.validate(step, "A" * 51)
        assert not result.is_valid

    def test_text_validation_strips_whitespace(self):
        """Test that text validation strips whitespace."""
        step = SurveyStep(
            id="ask_name",
            text="What's your name?",
            type=QuestionType.TEXT,
            next="completion"
        )

        result = InputValidator.validate(step, "  Alice  ")
        assert result.is_valid
        assert result.normalized_value == "Alice"

    def test_text_validation_custom_error_message(self):
        """Test that custom error messages are used."""
        step = SurveyStep(
            id="ask_name",
            text="What's your name?",
            type=QuestionType.TEXT,
            validation=ValidationRules(min_length=2),
            error_message="Name must be at least 2 characters!",
            next="completion"
        )

        result = InputValidator.validate(step, "A")
        assert not result.is_valid
        assert result.error_message == "Name must be at least 2 characters!"

    def test_regex_validation_valid(self):
        """Test regex validation with valid input."""
        step = SurveyStep(
            id="ask_zip",
            text="ZIP code?",
            type=QuestionType.REGEX,
            validation=ValidationRules(pattern=r'^\d{5}$'),
            next="completion"
        )

        result = InputValidator.validate(step, "12345")
        assert result.is_valid
        assert result.normalized_value == "12345"

    def test_regex_validation_invalid(self):
        """Test regex validation with invalid input."""
        step = SurveyStep(
            id="ask_zip",
            text="ZIP code?",
            type=QuestionType.REGEX,
            validation=ValidationRules(pattern=r'^\d{5}$'),
            next="completion"
        )

        # Too short
        result = InputValidator.validate(step, "1234")
        assert not result.is_valid

        # Contains letters
        result = InputValidator.validate(step, "abcde")
        assert not result.is_valid

        # Too long
        result = InputValidator.validate(step, "123456")
        assert not result.is_valid

    def test_regex_validation_email(self):
        """Test regex validation for email addresses."""
        step = SurveyStep(
            id="ask_email",
            text="Email?",
            type=QuestionType.REGEX,
            validation=ValidationRules(
                pattern=r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            ),
            next="completion"
        )

        # Valid emails
        assert InputValidator.validate(step, "user@example.com").is_valid
        assert InputValidator.validate(step, "test.user+tag@domain.co.uk").is_valid

        # Invalid emails
        assert not InputValidator.validate(step, "invalid").is_valid
        assert not InputValidator.validate(step, "@example.com").is_valid
        assert not InputValidator.validate(step, "user@").is_valid

    def test_regex_validation_custom_error_message(self):
        """Test regex with custom error message."""
        step = SurveyStep(
            id="ask_zip",
            text="ZIP code?",
            type=QuestionType.REGEX,
            validation=ValidationRules(pattern=r'^\d{5}$'),
            error_message="Please enter a 5-digit ZIP code.",
            next="completion"
        )

        result = InputValidator.validate(step, "abc")
        assert not result.is_valid
        assert result.error_message == "Please enter a 5-digit ZIP code."

    def test_choice_validation_valid(self):
        """Test choice validation with valid input."""
        step = SurveyStep(
            id="ask_consent",
            text="Consent?",
            type=QuestionType.CHOICE,
            validation=ValidationRules(
                choices=[
                    ChoiceOption(display="Yes", value="true"),
                    ChoiceOption(display="No", value="false"),
                ]
            ),
            next="completion"
        )

        # Exact match
        result = InputValidator.validate(step, "Yes")
        assert result.is_valid
        assert result.normalized_value == "true"  # Returns value, not display

        # Another option
        result = InputValidator.validate(step, "No")
        assert result.is_valid
        assert result.normalized_value == "false"

    def test_choice_validation_case_insensitive(self):
        """Test that choice validation is case-insensitive."""
        step = SurveyStep(
            id="ask_consent",
            text="Consent?",
            type=QuestionType.CHOICE,
            validation=ValidationRules(
                choices=[
                    ChoiceOption(display="Yes", value="true"),
                    ChoiceOption(display="No", value="false"),
                ]
            ),
            next="completion"
        )

        # Different cases
        assert InputValidator.validate(step, "yes").is_valid
        assert InputValidator.validate(step, "YES").is_valid
        assert InputValidator.validate(step, "YeS").is_valid
        assert InputValidator.validate(step, "no").is_valid

    def test_choice_validation_invalid(self):
        """Test choice validation with invalid input."""
        step = SurveyStep(
            id="ask_consent",
            text="Consent?",
            type=QuestionType.CHOICE,
            validation=ValidationRules(
                choices=[
                    ChoiceOption(display="Yes", value="true"),
                    ChoiceOption(display="No", value="false"),
                ]
            ),
            next="completion"
        )

        result = InputValidator.validate(step, "Maybe")
        assert not result.is_valid
        assert "Yes" in result.error_message
        assert "No" in result.error_message

    def test_choice_validation_custom_error_message(self):
        """Test choice with custom error message."""
        step = SurveyStep(
            id="ask_consent",
            text="Consent?",
            type=QuestionType.CHOICE,
            validation=ValidationRules(
                choices=[
                    ChoiceOption(display="Yes", value="true"),
                    ChoiceOption(display="No", value="false"),
                ]
            ),
            error_message="Please reply with Yes or No only.",
            next="completion"
        )

        result = InputValidator.validate(step, "Maybe")
        assert not result.is_valid
        assert result.error_message == "Please reply with Yes or No only."

    def test_choice_returns_value_not_display(self):
        """Test that choice validation returns value field."""
        step = SurveyStep(
            id="ask_volunteer",
            text="Volunteer?",
            type=QuestionType.CHOICE,
            validation=ValidationRules(
                choices=[
                    ChoiceOption(display="I want to volunteer", value="volunteer_yes"),
                    ChoiceOption(display="No thanks", value="volunteer_no"),
                ]
            ),
            next="completion"
        )

        result = InputValidator.validate(step, "I want to volunteer")
        assert result.is_valid
        assert result.normalized_value == "volunteer_yes"

        result = InputValidator.validate(step, "No thanks")
        assert result.is_valid
        assert result.normalized_value == "volunteer_no"

    def test_validation_strips_whitespace_all_types(self):
        """Test that all validators strip whitespace."""
        # Text
        text_step = SurveyStep(
            id="ask",
            text="?",
            type=QuestionType.TEXT,
            next="completion"
        )
        result = InputValidator.validate(text_step, "  value  ")
        assert result.normalized_value == "value"

        # Regex
        regex_step = SurveyStep(
            id="ask",
            text="?",
            type=QuestionType.REGEX,
            validation=ValidationRules(pattern=r'^\d{5}$'),
            next="completion"
        )
        result = InputValidator.validate(regex_step, "  12345  ")
        assert result.normalized_value == "12345"

        # Choice (whitespace stripped before matching)
        choice_step = SurveyStep(
            id="ask",
            text="?",
            type=QuestionType.CHOICE,
            validation=ValidationRules(
                choices=[ChoiceOption(display="Yes", value="true")]
            ),
            next="completion"
        )
        result = InputValidator.validate(choice_step, "  Yes  ")
        assert result.is_valid
