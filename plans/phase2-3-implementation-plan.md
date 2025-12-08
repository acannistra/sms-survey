# Phase 2 & 3 Implementation Plan: Survey Loading and Survey Engine

**Project:** SMS Survey Engine
**Phases:** Phase 2 (Survey Loading) and Phase 3 (Survey Engine Core Logic)
**Dependencies:** Phase 0 (Complete), Phase 1 (Complete)
**Created:** 2025-12-07

## Executive Summary

This plan details the implementation of the survey loading system (Phase 2) and survey engine core logic (Phase 3). Phase 2 establishes the foundation for YAML-based survey definitions with comprehensive validation, while Phase 3 implements the state machine that processes user responses, evaluates branching logic, and renders dynamic questions.

**Key Decisions:**
- Sequential implementation: Complete Phase 2 before Phase 3
- Use `simpleeval` library for safe expression evaluation (not Python's `eval()`)
- Implement comprehensive validation at multiple levels (schema, graph structure, runtime)
- Use `functools.lru_cache` for survey loading performance
- Jinja2 with `StrictUndefined` for template safety

## Phase 2: Survey Loading

### Overview

Phase 2 creates the survey-as-data infrastructure that allows non-technical staff to create and modify surveys without code changes. This includes Pydantic schemas for type safety, YAML loading with caching, validation services, and structural analysis.

### Architecture

```
surveys/*.yaml (YAML files)
    ↓
app/services/survey_loader.py (loads + validates)
    ↓
app/schemas/survey.py (Pydantic models)
    ↓
app/services/survey_validator.py (graph validation)
    ↓
app/services/validation.py (input validation)
```

---

## Task 2.1: Survey YAML Schema (app/schemas/survey.py)

### Purpose
Define Pydantic models that provide type safety, validation, and documentation for survey YAML structure.

### Implementation Details

**File:** `/Users/tony/Dropbox/Projects/sms-survey/app/schemas/survey.py`

**Structure:**

```python
"""Pydantic schemas for survey YAML definitions.

This module defines the structure and validation rules for survey YAML files.
All surveys must conform to these schemas to be loaded by the system.
"""

from typing import Optional, Literal
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
```

**Key Features:**
- Comprehensive validation at schema level
- Type safety with Pydantic
- Custom validators for complex rules
- Enum for question types
- Helper method for step lookup

**Testing Requirements:**
- Valid survey definitions parse correctly
- Invalid schemas raise descriptive errors
- Duplicate step IDs rejected
- Invalid references rejected
- Terminal steps without next validate
- Choice steps require choices
- Regex steps require pattern

---

## Task 2.2: Example Survey YAML (surveys/volunteer_signup.yaml)

### Purpose
Create a realistic example survey that demonstrates all features and serves as a test fixture.

### Implementation Details

**File:** `/Users/tony/Dropbox/Projects/sms-survey/surveys/volunteer_signup.yaml`

```yaml
# Volunteer Signup Survey
# Demonstrates: consent flow, mixed question types, conditional branching, templates

metadata:
  id: volunteer_signup
  name: Trail Volunteer Signup
  description: Collects volunteer interest and contact information for trail maintenance
  version: 1.0.0
  start_words:
    - volunteer
    - signup
    - join

consent:
  step_id: consent
  text: |
    Thanks for your interest! We'd like to collect your contact info.

    Reply YES to continue or NO to opt out.
  accept_values:
    - yes
    - y
    - sure
    - ok
    - okay
  decline_values:
    - no
    - n
    - nope
  decline_message: No problem! Text VOLUNTEER anytime to start over.

settings:
  max_retry_attempts: 3
  retry_exceeded_message: Too many invalid attempts. Let's move on.
  timeout_hours: 24

steps:
  - id: consent
    text: |
      Thanks for your interest! We'd like to collect your contact info.

      Reply YES to continue or NO to opt out.
    type: choice
    validation:
      choices:
        - display: "Yes"
          value: "true"
        - display: "No"
          value: "false"
    store_as: consent_given
    next: ask_name

  - id: ask_name
    text: Great! What's your first name?
    type: text
    validation:
      min_length: 2
      max_length: 50
    store_as: name
    error_message: Please enter a valid name (2-50 characters).
    next: ask_zip

  - id: ask_zip
    text: Thanks {{ name }}! What's your ZIP code?
    type: regex
    validation:
      pattern: '^\d{5}$'
    store_as: zip
    error_message: Please enter a 5-digit ZIP code.
    next: ask_volunteer

  - id: ask_volunteer
    text: Would you like to volunteer for trail maintenance?
    type: choice
    validation:
      choices:
        - display: "Yes"
          value: "true"
        - display: "No"
          value: "false"
    store_as: wants_volunteer
    next_conditional:
      - condition: wants_volunteer == 'true'
        next: ask_email
    next: ask_phone

  - id: ask_email
    text: Great! What's your email address?
    type: regex
    validation:
      pattern: '^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    store_as: email
    error_message: Please enter a valid email address.
    next: ask_phone

  - id: ask_phone
    text: What's your phone number? (10 digits)
    type: regex
    validation:
      pattern: '^\d{10}$'
    store_as: contact_phone
    error_message: Please enter a 10-digit phone number.
    next: completion

  - id: completion
    text: |
      Thanks {{ name }}! We've recorded your information.
      {% if wants_volunteer == 'true' %}
      We'll email you at {{ email }} with volunteer opportunities.
      {% else %}
      We'll keep you updated on trail conditions.
      {% endif %}

      Text STOP anytime to unsubscribe.
    type: terminal
```

**Key Features:**
- Demonstrates all question types (text, regex, choice, terminal)
- Conditional branching (email only if wants_volunteer)
- Jinja2 templates with context variables
- Realistic validation patterns
- Custom error messages

**Testing Requirements:**
- YAML loads without errors
- All steps validate
- Templates render correctly
- Branching logic works

---

## Task 2.3: Survey Loader Service (app/services/survey_loader.py)

### Purpose
Load and cache survey YAML files with comprehensive error handling.

### Implementation Details

**File:** `/Users/tony/Dropbox/Projects/sms-survey/app/services/survey_loader.py`

```python
"""Survey loader service with caching and validation.

This module loads survey definitions from YAML files, validates them against
Pydantic schemas, and caches the results for performance.
"""

import os
from pathlib import Path
from functools import lru_cache
from typing import Optional
import yaml
from pydantic import ValidationError

from app.schemas.survey import Survey, SurveyStep
from app.logging_config import get_logger

logger = get_logger(__name__)


class SurveyNotFoundError(Exception):
    """Raised when a survey file is not found."""
    pass


class SurveyValidationError(Exception):
    """Raised when a survey fails validation."""
    pass


class SurveyLoader:
    """Service for loading and caching survey definitions.

    Surveys are loaded from YAML files in the surveys/ directory and validated
    against Pydantic schemas. Results are cached for performance.
    """

    def __init__(self, surveys_dir: Optional[str] = None):
        """Initialize survey loader.

        Args:
            surveys_dir: Path to surveys directory (defaults to ./surveys)
        """
        if surveys_dir is None:
            # Default to surveys/ in project root
            project_root = Path(__file__).parent.parent.parent
            surveys_dir = project_root / "surveys"

        self.surveys_dir = Path(surveys_dir)

        if not self.surveys_dir.exists():
            logger.warning(f"Surveys directory not found: {self.surveys_dir}")

    @lru_cache(maxsize=128)
    def load_survey(self, survey_id: str) -> Survey:
        """Load and validate a survey from YAML file.

        Results are cached for performance. Clear cache with
        load_survey.cache_clear() if needed.

        Args:
            survey_id: Survey identifier (matches YAML filename without .yaml)

        Returns:
            Validated Survey object

        Raises:
            SurveyNotFoundError: If survey file doesn't exist
            SurveyValidationError: If survey fails validation

        Example:
            >>> loader = SurveyLoader()
            >>> survey = loader.load_survey("volunteer_signup")
            >>> print(survey.metadata.name)
            'Trail Volunteer Signup'
        """
        yaml_path = self.surveys_dir / f"{survey_id}.yaml"

        # Check if file exists
        if not yaml_path.exists():
            logger.error(f"Survey file not found: {yaml_path}")
            raise SurveyNotFoundError(f"Survey '{survey_id}' not found at {yaml_path}")

        # Load YAML
        try:
            with open(yaml_path, 'r') as f:
                raw_data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            logger.error(f"YAML parsing error for {survey_id}: {e}")
            raise SurveyValidationError(f"Invalid YAML in survey '{survey_id}': {e}")
        except Exception as e:
            logger.error(f"Error reading survey file {yaml_path}: {e}")
            raise SurveyValidationError(f"Error reading survey '{survey_id}': {e}")

        # Validate with Pydantic
        try:
            survey = Survey(**raw_data)
            logger.info(f"Successfully loaded survey: {survey_id} (version {survey.metadata.version})")
            return survey
        except ValidationError as e:
            logger.error(f"Validation error for survey {survey_id}: {e}")
            raise SurveyValidationError(f"Validation failed for survey '{survey_id}': {e}")

    def get_step(self, survey: Survey, step_id: str) -> Optional[SurveyStep]:
        """Get a specific step from a survey.

        Args:
            survey: Survey object
            step_id: Step identifier

        Returns:
            SurveyStep if found, None otherwise

        Example:
            >>> loader = SurveyLoader()
            >>> survey = loader.load_survey("volunteer_signup")
            >>> step = loader.get_step(survey, "ask_name")
            >>> print(step.text)
            "Great! What's your first name?"
        """
        return survey.get_step(step_id)

    def list_surveys(self) -> list[str]:
        """List all available survey IDs.

        Returns:
            List of survey IDs (filenames without .yaml extension)

        Example:
            >>> loader = SurveyLoader()
            >>> surveys = loader.list_surveys()
            >>> print(surveys)
            ['volunteer_signup', 'trail_feedback']
        """
        if not self.surveys_dir.exists():
            return []

        survey_files = self.surveys_dir.glob("*.yaml")
        survey_ids = [f.stem for f in survey_files]

        logger.debug(f"Found {len(survey_ids)} surveys: {survey_ids}")
        return sorted(survey_ids)

    def clear_cache(self):
        """Clear the survey cache.

        Useful during development or when surveys are updated at runtime.
        """
        self.load_survey.cache_clear()
        logger.info("Survey cache cleared")


# Global singleton instance
_loader_instance: Optional[SurveyLoader] = None


def get_survey_loader() -> SurveyLoader:
    """Get global SurveyLoader instance.

    Creates singleton instance on first call.

    Returns:
        Global SurveyLoader instance
    """
    global _loader_instance
    if _loader_instance is None:
        _loader_instance = SurveyLoader()
    return _loader_instance
```

**Key Features:**
- LRU cache for performance (128 surveys)
- Comprehensive error handling
- Singleton pattern for global access
- Path-agnostic (works in different environments)
- Detailed logging

**Testing Requirements:**
- Load valid surveys successfully
- Raise SurveyNotFoundError for missing files
- Raise SurveyValidationError for invalid YAML
- Cache works correctly
- list_surveys returns all YAML files
- clear_cache invalidates cache

---

## Task 2.4: Input Validation Service (app/services/validation.py)

### Purpose
Validate user input against survey step validation rules.

### Implementation Details

**File:** `/Users/tony/Dropbox/Projects/sms-survey/app/services/validation.py`

```python
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
```

**Key Features:**
- Type-specific validation logic
- Normalized values returned
- Custom or default error messages
- Case-insensitive choice matching
- Returns choice.value for storage

**Testing Requirements:**
- Text validation with min/max length
- Regex pattern matching
- Choice case-insensitive matching
- Choice returns value field
- Custom error messages used
- Default error messages generated
- Empty input handled

---

## Task 2.5: Survey Graph Validator (app/services/survey_validator.py)

### Purpose
Validate survey structure for reachability, cycles, and dangling references.

### Implementation Details

**File:** `/Users/tony/Dropbox/Projects/sms-survey/app/services/survey_validator.py`

```python
"""Survey graph validator for structural analysis.

This module validates the survey flow graph to ensure:
- All steps are reachable
- No circular references
- All next references are valid
- Terminal steps are properly configured
"""

from typing import Set, Dict, List, Optional
from collections import defaultdict, deque

from app.schemas.survey import Survey, SurveyStep, QuestionType
from app.logging_config import get_logger

logger = get_logger(__name__)


class SurveyStructureError(Exception):
    """Raised when survey structure is invalid."""
    pass


class SurveyValidator:
    """Service for validating survey flow graph structure."""

    @staticmethod
    def validate(survey: Survey) -> None:
        """Validate survey structure.

        Checks:
        1. All steps are reachable from first step
        2. No circular references (cycles)
        3. Terminal steps have no next
        4. Non-terminal steps have valid next or next_conditional
        5. All references point to existing steps

        Args:
            survey: Survey to validate

        Raises:
            SurveyStructureError: If structure is invalid

        Example:
            >>> survey = load_survey("volunteer_signup")
            >>> SurveyValidator.validate(survey)  # Raises if invalid
        """
        # Get first step (should be consent or first in list)
        if not survey.steps:
            raise SurveyStructureError("Survey has no steps")

        first_step = survey.steps[0]

        # Build adjacency graph
        graph = SurveyValidator._build_graph(survey)

        # Check for cycles
        if SurveyValidator._has_cycles(graph, first_step.id):
            raise SurveyStructureError("Survey contains circular references")

        # Check reachability
        reachable = SurveyValidator._get_reachable_steps(graph, first_step.id)
        all_step_ids = {step.id for step in survey.steps}
        unreachable = all_step_ids - reachable

        if unreachable:
            # Terminal steps being unreachable might be okay (alternative branches)
            # But log a warning for non-terminal unreachable steps
            non_terminal_unreachable = [
                step_id for step_id in unreachable
                if survey.get_step(step_id).type != QuestionType.TERMINAL
            ]
            if non_terminal_unreachable:
                logger.warning(f"Unreachable non-terminal steps: {non_terminal_unreachable}")

        logger.info(f"Survey {survey.metadata.id} validated successfully")

    @staticmethod
    def _build_graph(survey: Survey) -> Dict[str, List[str]]:
        """Build adjacency list representation of survey flow.

        Args:
            survey: Survey to analyze

        Returns:
            Dictionary mapping step_id -> list of next step IDs
        """
        graph = defaultdict(list)

        for step in survey.steps:
            # Add default next
            if step.next:
                graph[step.id].append(step.next)

            # Add conditional next
            if step.next_conditional:
                for cond in step.next_conditional:
                    graph[step.id].append(cond.next)

        return graph

    @staticmethod
    def _has_cycles(graph: Dict[str, List[str]], start_id: str) -> bool:
        """Detect cycles in survey flow using DFS.

        Args:
            graph: Adjacency list representation
            start_id: Starting step ID

        Returns:
            True if cycle detected, False otherwise
        """
        visited = set()
        rec_stack = set()

        def dfs(node: str) -> bool:
            """Depth-first search with recursion stack tracking."""
            visited.add(node)
            rec_stack.add(node)

            # Check all neighbors
            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    # Back edge found = cycle
                    return True

            rec_stack.remove(node)
            return False

        return dfs(start_id)

    @staticmethod
    def _get_reachable_steps(graph: Dict[str, List[str]], start_id: str) -> Set[str]:
        """Get all steps reachable from start using BFS.

        Args:
            graph: Adjacency list representation
            start_id: Starting step ID

        Returns:
            Set of reachable step IDs
        """
        reachable = {start_id}
        queue = deque([start_id])

        while queue:
            current = queue.popleft()

            for neighbor in graph.get(current, []):
                if neighbor not in reachable:
                    reachable.add(neighbor)
                    queue.append(neighbor)

        return reachable
```

**Key Features:**
- Graph-based structural analysis
- Cycle detection with DFS
- Reachability analysis with BFS
- Warnings for unreachable steps
- Comprehensive error messages

**Testing Requirements:**
- Valid surveys pass validation
- Circular references detected
- Unreachable steps identified
- Terminal steps validated
- Invalid references caught

---

## Phase 3: Survey Engine Core Logic

### Overview

Phase 3 implements the state machine that orchestrates the survey flow. This includes template rendering, conditional branching, and the main engine that coordinates all components.

### Architecture

```
User Input (SMS)
    ↓
app/services/survey_engine.py (orchestration)
    ↓
├─> app/services/validation.py (validate input)
├─> app/services/template_renderer.py (render questions)
└─> app/services/branching.py (evaluate conditions)
    ↓
Database Update (session, responses, context)
    ↓
Rendered Response (TwiML)
```

---

## Task 3.1: Template Renderer (app/services/template_renderer.py)

### Purpose
Render Jinja2 templates with survey context for dynamic question text.

### Implementation Details

**File:** `/Users/tony/Dropbox/Projects/sms-survey/app/services/template_renderer.py`

```python
"""Template rendering service using Jinja2.

This module renders survey question text with context variables using Jinja2.
Templates are rendered with StrictUndefined to catch missing variables early.
"""

from jinja2 import Environment, BaseLoader, StrictUndefined, TemplateError

from app.logging_config import get_logger

logger = get_logger(__name__)


class TemplateRenderError(Exception):
    """Raised when template rendering fails."""
    pass


class TemplateRenderer:
    """Service for rendering Jinja2 templates with survey context."""

    def __init__(self):
        """Initialize Jinja2 environment with strict settings."""
        self.env = Environment(
            loader=BaseLoader(),
            autoescape=True,  # Escape HTML/XML for security
            undefined=StrictUndefined,  # Raise error on undefined variables
        )

    def render(self, template_text: str, context: dict) -> str:
        """Render template with context variables.

        Args:
            template_text: Template string with Jinja2 syntax
            context: Dictionary of variables for template

        Returns:
            Rendered text

        Raises:
            TemplateRenderError: If template is invalid or variables are missing

        Example:
            >>> renderer = TemplateRenderer()
            >>> text = "Hello {{ name }}!"
            >>> result = renderer.render(text, {"name": "Alice"})
            >>> print(result)
            'Hello Alice!'
        """
        try:
            template = self.env.from_string(template_text)
            rendered = template.render(context)
            logger.debug(f"Rendered template successfully")
            return rendered
        except TemplateError as e:
            logger.error(f"Template rendering error: {e}")
            raise TemplateRenderError(f"Failed to render template: {e}")
        except Exception as e:
            logger.error(f"Unexpected error rendering template: {e}")
            raise TemplateRenderError(f"Unexpected error: {e}")


# Global singleton instance
_renderer_instance: Optional[TemplateRenderer] = None


def get_template_renderer() -> TemplateRenderer:
    """Get global TemplateRenderer instance.

    Returns:
        Global TemplateRenderer instance
    """
    global _renderer_instance
    if _renderer_instance is None:
        _renderer_instance = TemplateRenderer()
    return _renderer_instance
```

**Key Features:**
- StrictUndefined for safety
- Autoescape for security
- Singleton pattern
- Comprehensive error handling

**Testing Requirements:**
- Basic variable substitution
- Undefined variables raise errors
- Conditional blocks work
- For loops work
- Empty context handled
- Complex nested templates

---

## Task 3.2: Branching Logic (app/services/branching.py)

### Purpose
Safely evaluate conditional expressions for survey branching using simpleeval.

### Implementation Details

**File:** `/Users/tony/Dropbox/Projects/sms-survey/app/services/branching.py`

```python
"""Branching logic service using simpleeval for safe expression evaluation.

This module evaluates conditional expressions in survey definitions to determine
the next step based on user responses and context.
"""

from typing import Optional
from simpleeval import simple_eval, InvalidExpression

from app.schemas.survey import SurveyStep
from app.logging_config import get_logger

logger = get_logger(__name__)


class BranchingError(Exception):
    """Raised when branching evaluation fails."""
    pass


class BranchingService:
    """Service for evaluating conditional branching logic."""

    @staticmethod
    def evaluate_condition(condition: str, context: dict) -> bool:
        """Evaluate a conditional expression safely.

        Uses simpleeval library to safely evaluate Python expressions without
        arbitrary code execution risks.

        Supported operators:
        - Comparison: ==, !=, >, <, >=, <=, in, not in
        - Boolean: and, or, not
        - Parentheses for grouping

        Args:
            condition: Python expression string
            context: Dictionary of variables

        Returns:
            Boolean result of expression

        Raises:
            BranchingError: If expression is invalid or evaluation fails

        Example:
            >>> BranchingService.evaluate_condition("age >= 18", {"age": 25})
            True
            >>> BranchingService.evaluate_condition("wants_volunteer == 'true'", {"wants_volunteer": "true"})
            True
        """
        try:
            result = simple_eval(condition, names=context)

            # Ensure result is boolean
            if not isinstance(result, bool):
                logger.warning(f"Condition '{condition}' did not return boolean: {result}")
                return bool(result)

            logger.debug(f"Evaluated condition '{condition}' = {result}")
            return result
        except InvalidExpression as e:
            logger.error(f"Invalid expression '{condition}': {e}")
            raise BranchingError(f"Invalid condition expression: {e}")
        except NameError as e:
            logger.error(f"Undefined variable in condition '{condition}': {e}")
            raise BranchingError(f"Undefined variable in condition: {e}")
        except Exception as e:
            logger.error(f"Error evaluating condition '{condition}': {e}")
            raise BranchingError(f"Error evaluating condition: {e}")

    @staticmethod
    def determine_next_step(step: SurveyStep, context: dict) -> str:
        """Determine the next step ID based on conditional branching.

        Evaluates conditional branches in order. Returns the first matching
        condition's next step, or the default next step if no conditions match.

        Args:
            step: Current survey step
            context: Current survey context

        Returns:
            Next step ID

        Raises:
            BranchingError: If no valid next step can be determined

        Example:
            >>> step = SurveyStep(
            ...     id="ask_volunteer",
            ...     next="ask_phone",
            ...     next_conditional=[
            ...         ConditionalNext(condition="wants_volunteer == 'true'", next="ask_email")
            ...     ]
            ... )
            >>> BranchingService.determine_next_step(step, {"wants_volunteer": "true"})
            'ask_email'
        """
        # Check conditional branches first
        if step.next_conditional:
            for conditional in step.next_conditional:
                try:
                    if BranchingService.evaluate_condition(conditional.condition, context):
                        logger.info(f"Conditional branch matched: {conditional.condition} -> {conditional.next}")
                        return conditional.next
                except BranchingError:
                    # Log error but continue to next condition
                    logger.warning(f"Skipping invalid condition: {conditional.condition}")
                    continue

        # Fall back to default next
        if step.next:
            logger.debug(f"Using default next: {step.next}")
            return step.next

        # No next step found (should not happen for valid surveys)
        logger.error(f"No next step found for {step.id}")
        raise BranchingError(f"No valid next step for step {step.id}")
```

**Key Features:**
- Safe expression evaluation (no eval())
- Supports comparison and boolean operators
- Ordered condition evaluation
- Fallback to default next
- Detailed logging

**Dependencies:**
Add to `pyproject.toml`:
```toml
dependencies = [
    # ... existing ...
    "simpleeval>=1.0.2",
]
```

**Testing Requirements:**
- Simple comparisons work
- Boolean operators work
- In/not in operators work
- Undefined variables raise errors
- Invalid expressions raise errors
- Default next as fallback
- Multiple conditionals evaluated in order

---

## Task 3.3: Survey Engine (app/services/survey_engine.py)

### Purpose
Main orchestration service that coordinates all components to process survey flow.

### Implementation Details

**File:** `/Users/tony/Dropbox/Projects/sms-survey/app/services/survey_engine.py`

```python
"""Survey engine for orchestrating survey flow.

This module coordinates all survey components to process user responses,
update state, evaluate branching logic, and render responses.
"""

from typing import Tuple
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models.session import SurveySession
from app.models.response import SurveyResponse
from app.schemas.survey import QuestionType
from app.services.survey_loader import get_survey_loader, SurveyNotFoundError
from app.services.validation import InputValidator, ValidationResult
from app.services.template_renderer import get_template_renderer, TemplateRenderError
from app.services.branching import BranchingService, BranchingError
from app.logging_config import get_logger

logger = get_logger(__name__)


class SurveyEngineError(Exception):
    """Raised when survey engine encounters an error."""
    pass


class SurveyEngine:
    """Main survey orchestration service.

    Coordinates survey loading, validation, branching, rendering, and state
    management to process user responses and advance survey flow.
    """

    def __init__(self, db: Session):
        """Initialize survey engine.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db
        self.loader = get_survey_loader()
        self.renderer = get_template_renderer()

    def process_message(
        self,
        session: SurveySession,
        user_input: str
    ) -> Tuple[str, bool]:
        """Process user message and return response.

        Main entry point for survey flow. Handles:
        1. Load survey definition
        2. Handle consent if needed
        3. Validate user input
        4. Create response record
        5. Update context on valid input
        6. Evaluate branching logic
        7. Render next question
        8. Update session state

        Args:
            session: Current survey session (from database with FOR UPDATE lock)
            user_input: Raw user input from SMS

        Returns:
            Tuple of (response_text, is_completed)

        Raises:
            SurveyEngineError: If processing fails

        Example:
            >>> engine = SurveyEngine(db)
            >>> response, completed = engine.process_message(session, "Alice")
            >>> print(response)
            "Thanks Alice! What's your ZIP code?"
        """
        try:
            # Load survey
            survey = self.loader.load_survey(session.survey_id)

            # Get current step
            current_step = self.loader.get_step(survey, session.current_step)
            if current_step is None:
                logger.error(f"Step not found: {session.current_step}")
                raise SurveyEngineError(f"Invalid step: {session.current_step}")

            # Handle consent flow
            if not session.consent_given and current_step.id == survey.consent.step_id:
                return self._handle_consent(session, survey, user_input)

            # Validate input
            validation_result = InputValidator.validate(current_step, user_input)

            # Create response record
            self._record_response(
                session=session,
                step_id=current_step.id,
                user_input=user_input,
                validation_result=validation_result
            )

            # Handle validation failure
            if not validation_result.is_valid:
                return self._handle_validation_failure(session, survey, validation_result)

            # Valid input - update context
            if current_step.store_as:
                session.update_context(current_step.store_as, validation_result.normalized_value)
                logger.debug(f"Stored {current_step.store_as} = {validation_result.normalized_value}")

            # Determine next step
            next_step_id = BranchingService.determine_next_step(current_step, session.context)
            next_step = self.loader.get_step(survey, next_step_id)

            if next_step is None:
                logger.error(f"Next step not found: {next_step_id}")
                raise SurveyEngineError(f"Invalid next step: {next_step_id}")

            # Check if next step is terminal
            is_completed = (next_step.type == QuestionType.TERMINAL)

            # Render next step text
            response_text = self.renderer.render(next_step.text, session.context)

            # Update session state
            session.advance_step(next_step_id)
            if is_completed:
                session.mark_completed()

            # Commit changes
            self.db.commit()

            logger.info(f"Processed message for session {session.id}: {session.current_step}")
            return response_text, is_completed

        except (SurveyNotFoundError, TemplateRenderError, BranchingError) as e:
            logger.error(f"Survey engine error: {e}")
            self.db.rollback()
            raise SurveyEngineError(f"Processing failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in survey engine: {e}")
            self.db.rollback()
            raise SurveyEngineError(f"Unexpected error: {e}")

    def _handle_consent(
        self,
        session: SurveySession,
        survey: 'Survey',
        user_input: str
    ) -> Tuple[str, bool]:
        """Handle consent step processing.

        Args:
            session: Current session
            survey: Survey definition
            user_input: User's response

        Returns:
            Tuple of (response_text, is_completed)
        """
        normalized = user_input.strip().lower()

        # Check if accepted
        if normalized in survey.consent.accept_values:
            session.consent_given = True
            session.consent_given_at = datetime.now(timezone.utc)

            # Record consent response
            self._record_response(
                session=session,
                step_id=survey.consent.step_id,
                user_input=user_input,
                validation_result=ValidationResult(
                    is_valid=True,
                    normalized_value="accepted",
                    error_message=None
                )
            )

            # Move to first real step
            consent_step = self.loader.get_step(survey, survey.consent.step_id)
            next_step_id = consent_step.next
            next_step = self.loader.get_step(survey, next_step_id)

            session.advance_step(next_step_id)
            response_text = self.renderer.render(next_step.text, session.context)

            self.db.commit()
            logger.info(f"Consent accepted for session {session.id}")
            return response_text, False

        # Check if declined
        elif normalized in survey.consent.decline_values:
            # Mark session as completed without consent
            session.mark_completed()

            # Record decline response
            self._record_response(
                session=session,
                step_id=survey.consent.step_id,
                user_input=user_input,
                validation_result=ValidationResult(
                    is_valid=True,
                    normalized_value="declined",
                    error_message=None
                )
            )

            self.db.commit()
            logger.info(f"Consent declined for session {session.id}")
            return survey.consent.decline_message, True

        # Invalid consent response
        else:
            session.increment_retry()

            # Record invalid response
            self._record_response(
                session=session,
                step_id=survey.consent.step_id,
                user_input=user_input,
                validation_result=ValidationResult(
                    is_valid=False,
                    normalized_value=None,
                    error_message="Invalid consent response"
                )
            )

            self.db.commit()

            # Return consent text again
            return survey.consent.text, False

    def _handle_validation_failure(
        self,
        session: SurveySession,
        survey: 'Survey',
        validation_result: ValidationResult
    ) -> Tuple[str, bool]:
        """Handle validation failure with retry logic.

        Args:
            session: Current session
            survey: Survey definition
            validation_result: Failed validation result

        Returns:
            Tuple of (error_message, is_completed)
        """
        session.increment_retry()

        # Check if max retries exceeded
        if session.retry_count >= survey.settings.max_retry_attempts:
            logger.warning(f"Max retries exceeded for session {session.id}")

            # Get current step
            current_step = self.loader.get_step(survey, session.current_step)

            # Determine next step (skip current question)
            next_step_id = BranchingService.determine_next_step(current_step, session.context)
            next_step = self.loader.get_step(survey, next_step_id)

            # Move to next step
            session.advance_step(next_step_id)

            # Check if terminal
            is_completed = (next_step.type == QuestionType.TERMINAL)
            if is_completed:
                session.mark_completed()

            # Render next question
            next_text = self.renderer.render(next_step.text, session.context)

            self.db.commit()

            # Return retry exceeded message + next question
            return f"{survey.settings.retry_exceeded_message}\n\n{next_text}", is_completed

        # Still have retries left
        self.db.commit()
        return validation_result.error_message, False

    def _record_response(
        self,
        session: SurveySession,
        step_id: str,
        user_input: str,
        validation_result: ValidationResult
    ) -> None:
        """Record user response in database.

        Args:
            session: Current session
            step_id: Step being answered
            user_input: Raw user input
            validation_result: Validation result
        """
        response = SurveyResponse(
            session_id=session.id,
            step_id=step_id,
            response_text=user_input,
            stored_value=validation_result.normalized_value,
            is_valid=validation_result.is_valid
        )
        self.db.add(response)
        logger.debug(f"Recorded response for step {step_id}")
```

**Key Features:**
- Complete survey flow orchestration
- Consent handling
- Retry logic with max attempts
- Context management
- Database transactions with rollback
- Comprehensive error handling
- Logging at each step

**Testing Requirements:**
- Valid responses advance flow
- Invalid responses increment retry
- Max retries trigger skip
- Consent accepted advances
- Consent declined completes
- Context updated correctly
- Terminal steps mark completion
- Branching logic works
- Template rendering works
- Database transactions committed
- Errors trigger rollback

---

## Testing Strategy

### Unit Tests

**Phase 2 Unit Tests:**

1. **test_survey_schemas.py** (`/Users/tony/Dropbox/Projects/sms-survey/tests/unit/test_survey_schemas.py`)
   - Valid schemas parse correctly
   - Invalid schemas raise errors
   - Step validation works
   - Reference validation works
   - Duplicate IDs rejected

2. **test_survey_loader.py** (`/Users/tony/Dropbox/Projects/sms-survey/tests/unit/test_survey_loader.py`)
   - Load valid survey
   - Survey not found error
   - Invalid YAML error
   - Cache works
   - list_surveys returns all
   - get_step retrieves correct step

3. **test_validation.py** (`/Users/tony/Dropbox/Projects/sms-survey/tests/unit/test_validation.py`)
   - Text validation (min/max length)
   - Regex validation
   - Choice validation (case-insensitive)
   - Custom error messages
   - Default error messages

4. **test_survey_validator.py** (`/Users/tony/Dropbox/Projects/sms-survey/tests/unit/test_survey_validator.py`)
   - Valid survey passes
   - Circular reference detected
   - Unreachable steps identified

**Phase 3 Unit Tests:**

5. **test_template_renderer.py** (`/Users/tony/Dropbox/Projects/sms-survey/tests/unit/test_template_renderer.py`)
   - Basic variable substitution
   - Undefined variable error
   - Conditional blocks
   - For loops

6. **test_branching.py** (`/Users/tony/Dropbox/Projects/sms-survey/tests/unit/test_branching.py`)
   - Simple comparisons
   - Boolean operators
   - In/not in operators
   - Undefined variable error
   - Invalid expression error
   - determine_next_step logic

7. **test_survey_engine.py** (`/Users/tony/Dropbox/Projects/sms-survey/tests/unit/test_survey_engine.py`)
   - Process valid response
   - Process invalid response
   - Retry logic
   - Max retries exceeded
   - Consent accepted
   - Consent declined
   - Context updates
   - Terminal step completion
   - Branching integration

### Integration Tests

8. **test_survey_loading.py** (`/Users/tony/Dropbox/Projects/sms-survey/tests/integration/test_survey_loading.py`)
   - Load and validate example survey
   - All validation layers work together

9. **test_survey_flow.py** (`/Users/tony/Dropbox/Projects/sms-survey/tests/integration/test_survey_flow.py`)
   - Complete survey from consent to completion
   - Branching paths
   - Database persistence
   - Context across multiple steps

---

## Implementation Timeline

### Phase 2 (Survey Loading): ~4-6 hours
- Task 2.1 (Schemas): 1.5 hours
- Task 2.2 (Example YAML): 0.5 hours
- Task 2.3 (Loader): 1 hour
- Task 2.4 (Validation): 1.5 hours
- Task 2.5 (Graph Validator): 1 hour
- Testing: 1 hour

### Phase 3 (Survey Engine): ~4-6 hours
- Task 3.1 (Template Renderer): 0.5 hours
- Task 3.2 (Branching): 1 hour
- Task 3.3 (Survey Engine): 2.5 hours
- Testing: 2 hours

**Total Estimated Time: 8-12 hours**

---

## Dependency Installation

Add to `pyproject.toml`:
```toml
dependencies = [
    "fastapi[standard]==0.115.0",
    "sqlalchemy[asyncio]==2.0.36",
    "asyncpg==0.30.0",
    "alembic==1.13.3",
    "pydantic==2.9.2",
    "pydantic-settings==2.6.1",
    "twilio==9.3.7",
    "jinja2==3.1.4",
    "pyyaml==6.0.2",
    "python-multipart==0.0.17",
    "psycopg2-binary==2.9.10",
    "simpleeval>=1.0.2",  # NEW: Safe expression evaluation
]
```

Install with:
```bash
uv pip install -e ".[dev]"
```

---

## Success Criteria Checklist

### Phase 2 Completion:
- [ ] All Pydantic schemas validate correctly
- [ ] Example survey loads without errors
- [ ] Survey loader caches surveys
- [ ] Input validation works for all types
- [ ] Graph validator detects structural issues
- [ ] All Phase 2 unit tests pass
- [ ] Integration test for survey loading passes

### Phase 3 Completion:
- [ ] Template renderer works with Jinja2
- [ ] Branching evaluates conditions safely
- [ ] Survey engine processes complete flow
- [ ] Consent flow works correctly
- [ ] Retry logic functions properly
- [ ] Context updates persist
- [ ] All Phase 3 unit tests pass
- [ ] Integration test for complete flow passes
- [ ] Test coverage >80%

### Overall Integration:
- [ ] Complete survey flow from consent to completion
- [ ] Database records created correctly
- [ ] Branching paths work
- [ ] Templates render with context
- [ ] Error handling throughout
- [ ] Logging comprehensive

---

## Risk Mitigation

### Risk 1: Complex Jinja2 Templates Cause Errors
**Mitigation:** Use StrictUndefined to catch errors early, comprehensive template tests

### Risk 2: Simpleeval Library Limitations
**Mitigation:** Document supported operators, test edge cases, provide clear error messages

### Risk 3: Database Transaction Complexity
**Mitigation:** Use explicit commits/rollbacks, test error scenarios, use pessimistic locking

### Risk 4: Survey Graph Validation Performance
**Mitigation:** Cache validation results, use efficient graph algorithms (DFS/BFS)

---

## Next Steps After Completion

After Phase 2 & 3 are complete:
1. **Phase 4:** Twilio Integration (webhook schemas, TwiML generation)
2. **Phase 5:** FastAPI Routes (webhook endpoint, session management)
3. **Phase 6:** Deployment (Docker, Fly.io)

---

## Questions for Clarification

1. Should survey validation happen at startup or on-demand?
2. Should we cache rendered templates or re-render each time?
3. How should we handle survey version updates (migrate old sessions)?
4. Should we support functions in branching conditions (e.g., len(), str())?

---

## Appendix: File Structure

```
sms-survey/
├── app/
│   ├── schemas/
│   │   └── survey.py                    # NEW: Pydantic models
│   ├── services/
│   │   ├── survey_loader.py             # NEW: YAML loading
│   │   ├── validation.py                # NEW: Input validation
│   │   ├── survey_validator.py          # NEW: Graph validation
│   │   ├── template_renderer.py         # NEW: Jinja2 rendering
│   │   ├── branching.py                 # NEW: Conditional logic
│   │   └── survey_engine.py             # NEW: Main orchestration
├── surveys/
│   └── volunteer_signup.yaml            # NEW: Example survey
├── tests/
│   ├── unit/
│   │   ├── test_survey_schemas.py       # NEW
│   │   ├── test_survey_loader.py        # NEW
│   │   ├── test_validation.py           # NEW
│   │   ├── test_survey_validator.py     # NEW
│   │   ├── test_template_renderer.py    # NEW
│   │   ├── test_branching.py            # NEW
│   │   └── test_survey_engine.py        # NEW
│   └── integration/
│       ├── test_survey_loading.py       # NEW
│       └── test_survey_flow.py          # NEW
└── pyproject.toml                       # MODIFIED: Add simpleeval
```

---

**End of Implementation Plan**
