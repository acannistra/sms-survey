"""Unit tests for survey Pydantic schemas.

Tests validation logic for all survey schema components.
"""

import pytest
from pydantic import ValidationError

from app.schemas.survey import (
    QuestionType,
    ChoiceOption,
    ValidationRules,
    ConditionalNext,
    SurveyStep,
    ConsentConfig,
    SurveySettings,
    SurveyMetadata,
    Survey,
)


class TestChoiceOption:
    """Tests for ChoiceOption schema."""

    def test_valid_choice_option(self):
        """Test creating valid choice option."""
        choice = ChoiceOption(display="Yes", value="true")
        assert choice.display == "Yes"
        assert choice.value == "true"

    def test_empty_display_invalid(self):
        """Test that empty display is invalid."""
        with pytest.raises(ValidationError):
            ChoiceOption(display="", value="true")

    def test_empty_value_invalid(self):
        """Test that empty value is invalid."""
        with pytest.raises(ValidationError):
            ChoiceOption(display="Yes", value="")


class TestValidationRules:
    """Tests for ValidationRules schema."""

    def test_text_validation_rules(self):
        """Test text validation with min/max length."""
        rules = ValidationRules(min_length=2, max_length=50)
        assert rules.min_length == 2
        assert rules.max_length == 50
        assert rules.pattern is None
        assert rules.choices is None

    def test_regex_validation_rules(self):
        """Test regex validation with pattern."""
        rules = ValidationRules(pattern=r'^\d{5}$')
        assert rules.pattern == r'^\d{5}$'
        assert rules.min_length is None

    def test_choice_validation_rules(self):
        """Test choice validation with options."""
        rules = ValidationRules(
            choices=[
                ChoiceOption(display="Yes", value="true"),
                ChoiceOption(display="No", value="false"),
            ]
        )
        assert len(rules.choices) == 2

    def test_max_length_less_than_min_invalid(self):
        """Test that max_length < min_length is invalid."""
        with pytest.raises(ValidationError):
            ValidationRules(min_length=10, max_length=5)

    def test_max_length_equal_to_min_valid(self):
        """Test that max_length == min_length is valid."""
        rules = ValidationRules(min_length=5, max_length=5)
        assert rules.min_length == 5
        assert rules.max_length == 5


class TestConditionalNext:
    """Tests for ConditionalNext schema."""

    def test_valid_conditional(self):
        """Test creating valid conditional."""
        cond = ConditionalNext(
            condition="age >= 18",
            next="adult_path"
        )
        assert cond.condition == "age >= 18"
        assert cond.next == "adult_path"

    def test_empty_condition_invalid(self):
        """Test that empty condition is invalid."""
        with pytest.raises(ValidationError):
            ConditionalNext(condition="", next="next_step")


class TestSurveyStep:
    """Tests for SurveyStep schema."""

    def test_text_step(self):
        """Test creating text question step."""
        step = SurveyStep(
            id="ask_name",
            text="What's your name?",
            type=QuestionType.TEXT,
            validation=ValidationRules(min_length=2, max_length=50),
            store_as="name",
            next="ask_age"
        )
        assert step.id == "ask_name"
        assert step.type == QuestionType.TEXT
        assert step.next == "ask_age"

    def test_regex_step(self):
        """Test creating regex question step."""
        step = SurveyStep(
            id="ask_zip",
            text="ZIP code?",
            type=QuestionType.REGEX,
            validation=ValidationRules(pattern=r'^\d{5}$'),
            store_as="zip",
            next="completion"
        )
        assert step.type == QuestionType.REGEX
        assert step.validation.pattern == r'^\d{5}$'

    def test_choice_step(self):
        """Test creating choice question step."""
        step = SurveyStep(
            id="ask_consent",
            text="Do you consent?",
            type=QuestionType.CHOICE,
            validation=ValidationRules(
                choices=[
                    ChoiceOption(display="Yes", value="true"),
                    ChoiceOption(display="No", value="false"),
                ]
            ),
            store_as="consent",
            next="ask_name"
        )
        assert step.type == QuestionType.CHOICE
        assert len(step.validation.choices) == 2

    def test_terminal_step(self):
        """Test creating terminal step."""
        step = SurveyStep(
            id="completion",
            text="Thank you!",
            type=QuestionType.TERMINAL
        )
        assert step.type == QuestionType.TERMINAL
        assert step.next is None

    def test_terminal_with_next_invalid(self):
        """Test that terminal steps cannot have next."""
        with pytest.raises(ValidationError):
            SurveyStep(
                id="completion",
                text="Thank you!",
                type=QuestionType.TERMINAL,
                next="another_step"
            )

    def test_non_terminal_without_next_invalid(self):
        """Test that non-terminal steps must have next or next_conditional."""
        with pytest.raises(ValidationError):
            SurveyStep(
                id="ask_name",
                text="What's your name?",
                type=QuestionType.TEXT
            )

    def test_choice_without_choices_invalid(self):
        """Test that choice steps must have choices."""
        with pytest.raises(ValidationError):
            SurveyStep(
                id="ask_consent",
                text="Do you consent?",
                type=QuestionType.CHOICE,
                next="ask_name"
            )

    def test_regex_without_pattern_invalid(self):
        """Test that regex steps must have pattern."""
        with pytest.raises(ValidationError):
            SurveyStep(
                id="ask_zip",
                text="ZIP code?",
                type=QuestionType.REGEX,
                next="completion"
            )

    def test_conditional_branching(self):
        """Test step with conditional branching."""
        step = SurveyStep(
            id="ask_volunteer",
            text="Want to volunteer?",
            type=QuestionType.CHOICE,
            validation=ValidationRules(
                choices=[
                    ChoiceOption(display="Yes", value="true"),
                    ChoiceOption(display="No", value="false"),
                ]
            ),
            store_as="wants_volunteer",
            next_conditional=[
                ConditionalNext(condition="wants_volunteer == 'true'", next="ask_email")
            ],
            next="completion"
        )
        assert len(step.next_conditional) == 1
        assert step.next == "completion"


class TestConsentConfig:
    """Tests for ConsentConfig schema."""

    def test_valid_consent_config(self):
        """Test creating valid consent config."""
        consent = ConsentConfig(
            step_id="consent",
            text="Reply YES or NO",
            accept_values=["yes", "y"],
            decline_values=["no", "n"],
            decline_message="Goodbye!"
        )
        assert consent.step_id == "consent"
        assert "yes" in consent.accept_values

    def test_values_converted_to_lowercase(self):
        """Test that accept/decline values are converted to lowercase."""
        consent = ConsentConfig(
            step_id="consent",
            text="Reply YES or NO",
            accept_values=["YES", "Y"],
            decline_values=["NO", "N"],
            decline_message="Goodbye!"
        )
        assert consent.accept_values == ["yes", "y"]
        assert consent.decline_values == ["no", "n"]


class TestSurveySettings:
    """Tests for SurveySettings schema."""

    def test_default_settings(self):
        """Test default survey settings."""
        settings = SurveySettings()
        assert settings.max_retry_attempts == 3
        assert settings.timeout_hours == 24
        assert "Too many" in settings.retry_exceeded_message

    def test_custom_settings(self):
        """Test custom survey settings."""
        settings = SurveySettings(
            max_retry_attempts=5,
            retry_exceeded_message="Moving on...",
            timeout_hours=48
        )
        assert settings.max_retry_attempts == 5
        assert settings.timeout_hours == 48

    def test_invalid_max_retries(self):
        """Test that invalid max_retry_attempts are rejected."""
        with pytest.raises(ValidationError):
            SurveySettings(max_retry_attempts=0)

        with pytest.raises(ValidationError):
            SurveySettings(max_retry_attempts=11)


class TestSurveyMetadata:
    """Tests for SurveyMetadata schema."""

    def test_valid_metadata(self):
        """Test creating valid metadata."""
        metadata = SurveyMetadata(
            id="volunteer_signup",
            name="Volunteer Signup",
            description="Collect volunteer info",
            version="1.0.0",
            start_words=["volunteer", "signup"]
        )
        assert metadata.id == "volunteer_signup"
        assert metadata.version == "1.0.0"

    def test_start_words_lowercase(self):
        """Test that start words are converted to lowercase."""
        metadata = SurveyMetadata(
            id="test",
            name="Test",
            description="Test",
            version="1.0.0",
            start_words=["VOLUNTEER", "SignUp"]
        )
        assert metadata.start_words == ["volunteer", "signup"]

    def test_invalid_version_format(self):
        """Test that invalid version format is rejected."""
        with pytest.raises(ValidationError):
            SurveyMetadata(
                id="test",
                name="Test",
                description="Test",
                version="1.0",  # Missing patch version
                start_words=["test"]
            )

    def test_invalid_id_format(self):
        """Test that invalid ID format is rejected."""
        with pytest.raises(ValidationError):
            SurveyMetadata(
                id="test survey!",  # Contains space and special char
                name="Test",
                description="Test",
                version="1.0.0",
                start_words=["test"]
            )


class TestSurvey:
    """Tests for complete Survey schema."""

    def test_minimal_valid_survey(self):
        """Test creating minimal valid survey."""
        survey = Survey(
            metadata=SurveyMetadata(
                id="test",
                name="Test",
                description="Test",
                version="1.0.0",
                start_words=["test"]
            ),
            consent=ConsentConfig(
                step_id="consent",
                text="Reply YES or NO",
                accept_values=["yes"],
                decline_values=["no"],
                decline_message="Goodbye!"
            ),
            steps=[
                SurveyStep(
                    id="consent",
                    text="Reply YES or NO",
                    type=QuestionType.CHOICE,
                    validation=ValidationRules(
                        choices=[
                            ChoiceOption(display="Yes", value="true"),
                            ChoiceOption(display="No", value="false"),
                        ]
                    ),
                    next="completion"
                ),
                SurveyStep(
                    id="completion",
                    text="Done!",
                    type=QuestionType.TERMINAL
                )
            ]
        )
        assert len(survey.steps) == 2
        assert survey.settings.max_retry_attempts == 3  # Default

    def test_duplicate_step_ids_invalid(self):
        """Test that duplicate step IDs are rejected."""
        with pytest.raises(ValidationError, match="Duplicate step IDs"):
            Survey(
                metadata=SurveyMetadata(
                    id="test",
                    name="Test",
                    description="Test",
                    version="1.0.0",
                    start_words=["test"]
                ),
                consent=ConsentConfig(
                    step_id="consent",
                    text="Reply YES or NO",
                    accept_values=["yes"],
                    decline_values=["no"],
                    decline_message="Goodbye!"
                ),
                steps=[
                    SurveyStep(
                        id="consent",
                        text="Question 1",
                        type=QuestionType.TEXT,
                        next="consent"
                    ),
                    SurveyStep(
                        id="consent",  # Duplicate
                        text="Question 2",
                        type=QuestionType.TERMINAL
                    )
                ]
            )

    def test_invalid_consent_step_id(self):
        """Test that consent.step_id must exist in steps."""
        with pytest.raises(ValidationError, match="Consent step_id"):
            Survey(
                metadata=SurveyMetadata(
                    id="test",
                    name="Test",
                    description="Test",
                    version="1.0.0",
                    start_words=["test"]
                ),
                consent=ConsentConfig(
                    step_id="nonexistent",  # Doesn't exist
                    text="Reply YES or NO",
                    accept_values=["yes"],
                    decline_values=["no"],
                    decline_message="Goodbye!"
                ),
                steps=[
                    SurveyStep(
                        id="completion",
                        text="Done!",
                        type=QuestionType.TERMINAL
                    )
                ]
            )

    def test_invalid_next_reference(self):
        """Test that invalid next references are rejected."""
        with pytest.raises(ValidationError, match="Invalid step references"):
            Survey(
                metadata=SurveyMetadata(
                    id="test",
                    name="Test",
                    description="Test",
                    version="1.0.0",
                    start_words=["test"]
                ),
                consent=ConsentConfig(
                    step_id="consent",
                    text="Reply YES or NO",
                    accept_values=["yes"],
                    decline_values=["no"],
                    decline_message="Goodbye!"
                ),
                steps=[
                    SurveyStep(
                        id="consent",
                        text="Question",
                        type=QuestionType.TEXT,
                        next="nonexistent"  # Invalid reference
                    )
                ]
            )

    def test_get_step_method(self):
        """Test Survey.get_step() method."""
        survey = Survey(
            metadata=SurveyMetadata(
                id="test",
                name="Test",
                description="Test",
                version="1.0.0",
                start_words=["test"]
            ),
            consent=ConsentConfig(
                step_id="consent",
                text="Reply YES or NO",
                accept_values=["yes"],
                decline_values=["no"],
                decline_message="Goodbye!"
            ),
            steps=[
                SurveyStep(
                    id="consent",
                    text="Reply YES or NO",
                    type=QuestionType.CHOICE,
                    validation=ValidationRules(
                        choices=[
                            ChoiceOption(display="Yes", value="true"),
                            ChoiceOption(display="No", value="false"),
                        ]
                    ),
                    next="completion"
                ),
                SurveyStep(
                    id="completion",
                    text="Done!",
                    type=QuestionType.TERMINAL
                )
            ]
        )

        # Test finding existing step
        step = survey.get_step("consent")
        assert step is not None
        assert step.id == "consent"

        # Test not finding nonexistent step
        step = survey.get_step("nonexistent")
        assert step is None
