"""Pydantic schemas for survey YAML definitions.

This module defines the structure and validation rules for survey YAML files.
All surveys must conform to these schemas to be loaded by the system.
"""

from typing import Optional
from pydantic import BaseModel, Field, field_validator, model_validator
from enum import Enum


class QuestionType(str, Enum):
    """Valid question types in survey definitions."""
    TEXT = "text"
    REGEX = "regex"
    CHOICE = "choice"
    TERMINAL = "terminal"


class ChoiceOption(BaseModel):
    """A single choice option for choice-type questions.

    Attributes:
        display: Text shown to user (e.g., "Yes", "No")
        value: Value stored in context (e.g., "true", "false")
    """
    display: str = Field(..., min_length=1, description="Display text for choice")
    value: str = Field(..., min_length=1, description="Value stored in context")


class ValidationRules(BaseModel):
    """Validation rules for question responses.

    Different question types use different validation fields:
    - text: min_length, max_length
    - regex: pattern
    - choice: choices
    - terminal: no validation
    """
    min_length: Optional[int] = Field(None, ge=1, description="Minimum text length")
    max_length: Optional[int] = Field(None, ge=1, description="Maximum text length")
    pattern: Optional[str] = Field(None, description="Regex pattern for validation")
    choices: Optional[list[ChoiceOption]] = Field(None, description="Valid choices")

    @field_validator('max_length')
    @classmethod
    def max_length_greater_than_min(cls, v, info):
        """Ensure max_length > min_length if both are set."""
        if v is not None and info.data.get('min_length') is not None:
            if v < info.data['min_length']:
                raise ValueError('max_length must be >= min_length')
        return v


class ConditionalNext(BaseModel):
    """Conditional branching definition.

    Allows surveys to branch based on user responses.
    Example: If user said "yes" to volunteering, ask for email.

    Attributes:
        condition: Python expression evaluated with context (e.g., "wants_volunteer == 'true'")
        next: Step ID to navigate to if condition is true
    """
    condition: str = Field(..., min_length=1, description="Python expression for branching")
    next: str = Field(..., min_length=1, description="Step ID if condition is true")


class SurveyStep(BaseModel):
    """A single step in the survey flow.

    Steps can be questions (text, regex, choice) or terminal messages.

    Attributes:
        id: Unique identifier for this step
        text: Question text or message (supports Jinja2 templates)
        type: Question type (text/regex/choice/terminal)
        validation: Validation rules for user input
        store_as: Context variable name to store response
        next: Default next step ID
        next_conditional: List of conditional branches
        error_message: Custom error message for validation failure
    """
    id: str = Field(..., min_length=1, description="Unique step identifier")
    text: str = Field(..., min_length=1, description="Question text with optional Jinja2 templates")
    type: QuestionType = Field(..., description="Question type")
    validation: Optional[ValidationRules] = Field(None, description="Validation rules")
    store_as: Optional[str] = Field(None, description="Context variable name")
    next: Optional[str] = Field(None, description="Next step ID")
    next_conditional: Optional[list[ConditionalNext]] = Field(None, description="Conditional branching")
    error_message: Optional[str] = Field(None, description="Custom validation error message")

    @model_validator(mode='after')
    def validate_step_requirements(self):
        """Validate step-specific requirements based on type."""
        # Terminal steps should not have next
        if self.type == QuestionType.TERMINAL:
            if self.next is not None or self.next_conditional is not None:
                raise ValueError("Terminal steps cannot have 'next' or 'next_conditional'")

        # Non-terminal steps must have next or next_conditional
        if self.type != QuestionType.TERMINAL:
            if self.next is None and self.next_conditional is None:
                raise ValueError(f"Step '{self.id}' must have 'next' or 'next_conditional'")

        # Choice steps must have choices in validation
        if self.type == QuestionType.CHOICE:
            if self.validation is None or self.validation.choices is None:
                raise ValueError(f"Choice step '{self.id}' must have validation.choices")

        # Regex steps must have pattern in validation
        if self.type == QuestionType.REGEX:
            if self.validation is None or self.validation.pattern is None:
                raise ValueError(f"Regex step '{self.id}' must have validation.pattern")

        return self


class ConsentConfig(BaseModel):
    """Consent flow configuration.

    Defines how consent is requested and processed.

    Attributes:
        step_id: ID of consent step (usually "consent")
        text: Consent request message
        accept_values: List of responses that mean "yes" (case-insensitive)
        decline_values: List of responses that mean "no" (case-insensitive)
        decline_message: Message sent when user declines
    """
    step_id: str = Field(..., min_length=1, description="Consent step ID")
    text: str = Field(..., min_length=1, description="Consent request message")
    accept_values: list[str] = Field(..., min_length=1, description="Values that mean 'yes'")
    decline_values: list[str] = Field(..., min_length=1, description="Values that mean 'no'")
    decline_message: str = Field(..., min_length=1, description="Message for declined consent")

    @field_validator('accept_values', 'decline_values')
    @classmethod
    def values_lowercase(cls, v):
        """Ensure all accept/decline values are lowercase for comparison."""
        return [val.lower() for val in v]


class SurveySettings(BaseModel):
    """Global survey settings.

    Attributes:
        max_retry_attempts: Number of retries before moving on
        retry_exceeded_message: Message when max retries exceeded
        timeout_hours: Hours before session expires
    """
    max_retry_attempts: int = Field(default=3, ge=1, le=10, description="Max validation retries")
    retry_exceeded_message: str = Field(
        default="Too many invalid attempts. Moving to the next question.",
        description="Message when retries exceeded"
    )
    timeout_hours: int = Field(default=24, ge=1, le=168, description="Session timeout in hours")


class SurveyMetadata(BaseModel):
    """Survey metadata and identification.

    Attributes:
        id: Unique survey identifier (matches YAML filename)
        name: Human-readable survey name
        description: Survey description
        version: Survey version (semantic versioning)
        start_words: Trigger words to start this survey (lowercase)
    """
    id: str = Field(..., min_length=1, description="Survey identifier")
    name: str = Field(..., min_length=1, description="Survey name")
    description: str = Field(..., min_length=1, description="Survey description")
    version: str = Field(..., pattern=r'^\d+\.\d+\.\d+$', description="Semantic version")
    start_words: list[str] = Field(..., min_length=1, description="Trigger words")

    @field_validator('start_words')
    @classmethod
    def start_words_lowercase(cls, v):
        """Ensure all start words are lowercase for comparison."""
        return [word.lower() for word in v]

    @field_validator('id')
    @classmethod
    def id_alphanumeric(cls, v):
        """Ensure ID is alphanumeric with underscores/hyphens only."""
        if not v.replace('_', '').replace('-', '').isalnum():
            raise ValueError('Survey ID must be alphanumeric with underscores/hyphens')
        return v


class Survey(BaseModel):
    """Complete survey definition.

    Root schema for survey YAML files.

    Attributes:
        metadata: Survey identification and metadata
        consent: Consent flow configuration
        settings: Global survey settings
        steps: List of survey steps
    """
    metadata: SurveyMetadata
    consent: ConsentConfig
    settings: SurveySettings = Field(default_factory=SurveySettings)
    steps: list[SurveyStep] = Field(..., min_length=1)

    @model_validator(mode='after')
    def validate_survey_structure(self):
        """Validate overall survey structure and references."""
        # Check for duplicate step IDs
        step_ids = [step.id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            duplicates = [sid for sid in step_ids if step_ids.count(sid) > 1]
            raise ValueError(f"Duplicate step IDs found: {duplicates}")

        # Check that consent.step_id exists in steps
        if self.consent.step_id not in step_ids:
            raise ValueError(f"Consent step_id '{self.consent.step_id}' not found in steps")

        # Collect all referenced next step IDs
        referenced_ids = set()
        for step in self.steps:
            if step.next:
                referenced_ids.add(step.next)
            if step.next_conditional:
                for cond in step.next_conditional:
                    referenced_ids.add(cond.next)

        # Check that all referenced IDs exist
        invalid_refs = referenced_ids - set(step_ids)
        if invalid_refs:
            raise ValueError(f"Invalid step references: {invalid_refs}")

        return self

    def get_step(self, step_id: str) -> Optional[SurveyStep]:
        """Get step by ID.

        Args:
            step_id: Step identifier

        Returns:
            SurveyStep if found, None otherwise
        """
        for step in self.steps:
            if step.id == step_id:
                return step
        return None
