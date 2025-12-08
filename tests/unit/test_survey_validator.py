"""Unit tests for survey graph validator.

Tests structural validation of survey flow.
"""

import pytest

from app.services.survey_validator import SurveyValidator, SurveyStructureError
from app.schemas.survey import (
    Survey,
    SurveyMetadata,
    ConsentConfig,
    SurveySettings,
    SurveyStep,
    QuestionType,
    ValidationRules,
    ChoiceOption,
    ConditionalNext,
)


class TestSurveyValidator:
    """Tests for SurveyValidator class."""

    @pytest.fixture
    def valid_linear_survey(self):
        """Create a valid linear survey."""
        return Survey(
            metadata=SurveyMetadata(
                id="linear",
                name="Linear Survey",
                description="Simple linear flow",
                version="1.0.0",
                start_words=["test"]
            ),
            consent=ConsentConfig(
                step_id="consent",
                text="Consent?",
                accept_values=["yes"],
                decline_values=["no"],
                decline_message="Goodbye"
            ),
            steps=[
                SurveyStep(
                    id="consent",
                    text="Consent?",
                    type=QuestionType.CHOICE,
                    validation=ValidationRules(
                        choices=[
                            ChoiceOption(display="Yes", value="true"),
                            ChoiceOption(display="No", value="false"),
                        ]
                    ),
                    next="ask_name"
                ),
                SurveyStep(
                    id="ask_name",
                    text="Name?",
                    type=QuestionType.TEXT,
                    next="completion"
                ),
                SurveyStep(
                    id="completion",
                    text="Done!",
                    type=QuestionType.TERMINAL
                )
            ]
        )

    @pytest.fixture
    def valid_branching_survey(self):
        """Create a valid survey with conditional branching."""
        return Survey(
            metadata=SurveyMetadata(
                id="branching",
                name="Branching Survey",
                description="Survey with branches",
                version="1.0.0",
                start_words=["test"]
            ),
            consent=ConsentConfig(
                step_id="consent",
                text="Consent?",
                accept_values=["yes"],
                decline_values=["no"],
                decline_message="Goodbye"
            ),
            steps=[
                SurveyStep(
                    id="consent",
                    text="Consent?",
                    type=QuestionType.CHOICE,
                    validation=ValidationRules(
                        choices=[
                            ChoiceOption(display="Yes", value="true"),
                            ChoiceOption(display="No", value="false"),
                        ]
                    ),
                    next="ask_volunteer"
                ),
                SurveyStep(
                    id="ask_volunteer",
                    text="Volunteer?",
                    type=QuestionType.CHOICE,
                    validation=ValidationRules(
                        choices=[
                            ChoiceOption(display="Yes", value="true"),
                            ChoiceOption(display="No", value="false"),
                        ]
                    ),
                    next_conditional=[
                        ConditionalNext(
                            condition="wants_volunteer == 'true'",
                            next="ask_email"
                        )
                    ],
                    next="completion"
                ),
                SurveyStep(
                    id="ask_email",
                    text="Email?",
                    type=QuestionType.TEXT,
                    next="completion"
                ),
                SurveyStep(
                    id="completion",
                    text="Done!",
                    type=QuestionType.TERMINAL
                )
            ]
        )

    @pytest.fixture
    def circular_survey(self):
        """Create a survey with circular reference."""
        return Survey(
            metadata=SurveyMetadata(
                id="circular",
                name="Circular Survey",
                description="Has circular reference",
                version="1.0.0",
                start_words=["test"]
            ),
            consent=ConsentConfig(
                step_id="consent",
                text="Consent?",
                accept_values=["yes"],
                decline_values=["no"],
                decline_message="Goodbye"
            ),
            steps=[
                SurveyStep(
                    id="consent",
                    text="Consent?",
                    type=QuestionType.CHOICE,
                    validation=ValidationRules(
                        choices=[
                            ChoiceOption(display="Yes", value="true"),
                            ChoiceOption(display="No", value="false"),
                        ]
                    ),
                    next="step1"
                ),
                SurveyStep(
                    id="step1",
                    text="Step 1",
                    type=QuestionType.TEXT,
                    next="step2"
                ),
                SurveyStep(
                    id="step2",
                    text="Step 2",
                    type=QuestionType.TEXT,
                    next="step1"  # Circular reference back to step1
                )
            ]
        )

    @pytest.fixture
    def unreachable_steps_survey(self):
        """Create a survey with unreachable steps."""
        return Survey(
            metadata=SurveyMetadata(
                id="unreachable",
                name="Unreachable Survey",
                description="Has unreachable steps",
                version="1.0.0",
                start_words=["test"]
            ),
            consent=ConsentConfig(
                step_id="consent",
                text="Consent?",
                accept_values=["yes"],
                decline_values=["no"],
                decline_message="Goodbye"
            ),
            steps=[
                SurveyStep(
                    id="consent",
                    text="Consent?",
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
                    id="orphaned_step",  # Never referenced, unreachable
                    text="Orphaned",
                    type=QuestionType.TEXT,
                    next="completion"
                ),
                SurveyStep(
                    id="completion",
                    text="Done!",
                    type=QuestionType.TERMINAL
                )
            ]
        )

    def test_valid_linear_survey_passes(self, valid_linear_survey):
        """Test that a valid linear survey passes validation."""
        # Should not raise exception
        SurveyValidator.validate(valid_linear_survey)

    def test_valid_branching_survey_passes(self, valid_branching_survey):
        """Test that a valid branching survey passes validation."""
        # Should not raise exception
        SurveyValidator.validate(valid_branching_survey)

    def test_circular_reference_detected(self, circular_survey):
        """Test that circular references are detected."""
        with pytest.raises(SurveyStructureError, match="circular"):
            SurveyValidator.validate(circular_survey)

    def test_self_reference_detected(self):
        """Test that self-references (step pointing to itself) are detected."""
        survey = Survey(
            metadata=SurveyMetadata(
                id="self_ref",
                name="Self Reference",
                description="Step points to itself",
                version="1.0.0",
                start_words=["test"]
            ),
            consent=ConsentConfig(
                step_id="consent",
                text="Consent?",
                accept_values=["yes"],
                decline_values=["no"],
                decline_message="Goodbye"
            ),
            steps=[
                SurveyStep(
                    id="consent",
                    text="Consent?",
                    type=QuestionType.TEXT,
                    next="consent"  # Points to itself
                )
            ]
        )

        with pytest.raises(SurveyStructureError, match="circular"):
            SurveyValidator.validate(survey)

    def test_unreachable_non_terminal_steps_logged(self, unreachable_steps_survey, caplog):
        """Test that unreachable non-terminal steps generate warnings."""
        import logging
        caplog.set_level(logging.WARNING)

        # Should not raise exception, but should log warning
        SurveyValidator.validate(unreachable_steps_survey)

        # Check that warning was logged
        assert any("Unreachable" in record.message for record in caplog.records)
        assert any("orphaned_step" in record.message for record in caplog.records)

    def test_unreachable_terminal_steps_ok(self):
        """Test that unreachable terminal steps are allowed (alternative endings)."""
        survey = Survey(
            metadata=SurveyMetadata(
                id="alt_endings",
                name="Alternative Endings",
                description="Multiple terminal steps",
                version="1.0.0",
                start_words=["test"]
            ),
            consent=ConsentConfig(
                step_id="consent",
                text="Consent?",
                accept_values=["yes"],
                decline_values=["no"],
                decline_message="Goodbye"
            ),
            steps=[
                SurveyStep(
                    id="consent",
                    text="Consent?",
                    type=QuestionType.CHOICE,
                    validation=ValidationRules(
                        choices=[
                            ChoiceOption(display="Yes", value="true"),
                            ChoiceOption(display="No", value="false"),
                        ]
                    ),
                    next="completion1"
                ),
                SurveyStep(
                    id="completion1",
                    text="Thanks!",
                    type=QuestionType.TERMINAL
                ),
                SurveyStep(
                    id="completion2",  # Alternative ending, unreachable
                    text="Goodbye!",
                    type=QuestionType.TERMINAL
                )
            ]
        )

        # Should not raise exception
        SurveyValidator.validate(survey)

    def test_empty_survey_invalid(self):
        """Test that survey with no steps is invalid."""
        # This should be caught by Pydantic, but test anyway
        with pytest.raises(ValidationError):
            Survey(
                metadata=SurveyMetadata(
                    id="empty",
                    name="Empty",
                    description="No steps",
                    version="1.0.0",
                    start_words=["test"]
                ),
                consent=ConsentConfig(
                    step_id="consent",
                    text="Consent?",
                    accept_values=["yes"],
                    decline_values=["no"],
                    decline_message="Goodbye"
                ),
                steps=[]
            )

    def test_complex_branching_no_cycles(self):
        """Test complex branching without cycles."""
        survey = Survey(
            metadata=SurveyMetadata(
                id="complex",
                name="Complex",
                description="Complex branching",
                version="1.0.0",
                start_words=["test"]
            ),
            consent=ConsentConfig(
                step_id="consent",
                text="Consent?",
                accept_values=["yes"],
                decline_values=["no"],
                decline_message="Goodbye"
            ),
            steps=[
                SurveyStep(
                    id="consent",
                    text="?",
                    type=QuestionType.CHOICE,
                    validation=ValidationRules(
                        choices=[
                            ChoiceOption(display="Yes", value="true"),
                            ChoiceOption(display="No", value="false"),
                        ]
                    ),
                    next="q1"
                ),
                SurveyStep(
                    id="q1",
                    text="?",
                    type=QuestionType.CHOICE,
                    validation=ValidationRules(
                        choices=[
                            ChoiceOption(display="A", value="a"),
                            ChoiceOption(display="B", value="b"),
                        ]
                    ),
                    next_conditional=[
                        ConditionalNext(condition="x == 'a'", next="q2a")
                    ],
                    next="q2b"
                ),
                SurveyStep(
                    id="q2a",
                    text="?",
                    type=QuestionType.TEXT,
                    next="completion"
                ),
                SurveyStep(
                    id="q2b",
                    text="?",
                    type=QuestionType.TEXT,
                    next="completion"
                ),
                SurveyStep(
                    id="completion",
                    text="Done!",
                    type=QuestionType.TERMINAL
                )
            ]
        )

        # Should pass validation
        SurveyValidator.validate(survey)

    def test_build_graph(self, valid_branching_survey):
        """Test graph building from survey."""
        graph = SurveyValidator._build_graph(valid_branching_survey)

        assert "consent" in graph
        assert "ask_volunteer" in graph
        assert "ask_volunteer" in graph["consent"]
        assert "ask_email" in graph["ask_volunteer"]
        assert "completion" in graph["ask_volunteer"]

    def test_has_cycles_detects_cycle(self):
        """Test cycle detection algorithm."""
        graph = {
            "a": ["b"],
            "b": ["c"],
            "c": ["a"]  # Cycle back to a
        }

        assert SurveyValidator._has_cycles(graph, "a")

    def test_has_cycles_no_cycle(self):
        """Test cycle detection on acyclic graph."""
        graph = {
            "a": ["b"],
            "b": ["c"],
            "c": []
        }

        assert not SurveyValidator._has_cycles(graph, "a")

    def test_get_reachable_steps(self):
        """Test reachability calculation."""
        graph = {
            "a": ["b", "c"],
            "b": ["d"],
            "c": ["d"],
            "d": [],
            "e": []  # Unreachable
        }

        reachable = SurveyValidator._get_reachable_steps(graph, "a")

        assert "a" in reachable
        assert "b" in reachable
        assert "c" in reachable
        assert "d" in reachable
        assert "e" not in reachable


# Import ValidationError for the empty survey test
from pydantic import ValidationError
