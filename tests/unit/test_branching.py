"""Unit tests for branching logic service.

Tests safe expression evaluation with simpleeval.
"""

import pytest

from app.services.branching import BranchingService, BranchingError
from app.schemas.survey import SurveyStep, QuestionType, ConditionalNext


class TestBranchingService:
    """Tests for BranchingService class."""

    def test_simple_equality_comparison(self):
        """Test simple equality comparisons."""
        # String equality
        assert BranchingService.evaluate_condition(
            "name == 'Alice'",
            {"name": "Alice"}
        ) is True

        assert BranchingService.evaluate_condition(
            "name == 'Bob'",
            {"name": "Alice"}
        ) is False

    def test_inequality_comparison(self):
        """Test inequality comparisons."""
        assert BranchingService.evaluate_condition(
            "age != 18",
            {"age": 25}
        ) is True

        assert BranchingService.evaluate_condition(
            "age != 25",
            {"age": 25}
        ) is False

    def test_numeric_comparisons(self):
        """Test numeric comparison operators."""
        context = {"age": 25, "min_age": 18, "max_age": 65}

        # Greater than
        assert BranchingService.evaluate_condition("age > min_age", context) is True
        assert BranchingService.evaluate_condition("age > 30", context) is False

        # Less than
        assert BranchingService.evaluate_condition("age < max_age", context) is True
        assert BranchingService.evaluate_condition("age < 20", context) is False

        # Greater than or equal
        assert BranchingService.evaluate_condition("age >= 25", context) is True
        assert BranchingService.evaluate_condition("age >= 26", context) is False

        # Less than or equal
        assert BranchingService.evaluate_condition("age <= 25", context) is True
        assert BranchingService.evaluate_condition("age <= 24", context) is False

    def test_boolean_and_operator(self):
        """Test boolean AND operator."""
        context = {"age": 25, "has_license": True}

        assert BranchingService.evaluate_condition(
            "age >= 18 and has_license",
            context
        ) is True

        assert BranchingService.evaluate_condition(
            "age >= 30 and has_license",
            context
        ) is False

    def test_boolean_or_operator(self):
        """Test boolean OR operator."""
        context = {"age": 25, "is_student": False}

        assert BranchingService.evaluate_condition(
            "age < 18 or is_student",
            context
        ) is False

        assert BranchingService.evaluate_condition(
            "age > 18 or is_student",
            context
        ) is True

    def test_boolean_not_operator(self):
        """Test boolean NOT operator."""
        context = {"is_member": False}

        assert BranchingService.evaluate_condition(
            "not is_member",
            context
        ) is True

        context = {"is_member": True}
        assert BranchingService.evaluate_condition(
            "not is_member",
            context
        ) is False

    def test_multiple_or_conditions(self):
        """Test multiple OR conditions (alternative to 'in' operator)."""
        context = {"response": "yes"}

        # Simulate 'in' with multiple 'or' conditions
        assert BranchingService.evaluate_condition(
            "response == 'yes' or response == 'y' or response == 'sure'",
            context
        ) is True

        assert BranchingService.evaluate_condition(
            "response == 'no' or response == 'n'",
            context
        ) is False

    def test_parentheses_grouping(self):
        """Test parentheses for grouping expressions."""
        context = {"age": 25, "is_student": True, "has_id": True}

        assert BranchingService.evaluate_condition(
            "(age > 18 and is_student) or has_id",
            context
        ) is True

        assert BranchingService.evaluate_condition(
            "age > 18 and (is_student or has_id)",
            context
        ) is True

    def test_undefined_variable_raises_error(self):
        """Test that undefined variables raise BranchingError."""
        with pytest.raises(BranchingError):
            BranchingService.evaluate_condition(
                "undefined_var == 'test'",
                {}
            )

    def test_invalid_expression_raises_error(self):
        """Test that invalid expressions raise BranchingError."""
        with pytest.raises(BranchingError):
            BranchingService.evaluate_condition(
                "age === 25",  # Invalid operator
                {"age": 25}
            )

    def test_non_boolean_result_converted(self):
        """Test that non-boolean results are converted to boolean."""
        # Truthy value
        result = BranchingService.evaluate_condition(
            "1 + 1",
            {}
        )
        assert result is True

        # Falsy value (0)
        result = BranchingService.evaluate_condition(
            "1 - 1",
            {}
        )
        assert result is False

    def test_string_comparisons_case_sensitive(self):
        """Test that string comparisons are case-sensitive."""
        context = {"response": "Yes"}

        assert BranchingService.evaluate_condition(
            "response == 'Yes'",
            context
        ) is True

        assert BranchingService.evaluate_condition(
            "response == 'yes'",
            context
        ) is False

    def test_complex_realistic_conditions(self):
        """Test realistic survey branching conditions."""
        # Volunteer flow
        context = {"wants_volunteer": "true", "age": 25}
        assert BranchingService.evaluate_condition(
            "wants_volunteer == 'true'",
            context
        ) is True

        # Age-based branching
        context = {"age": 17}
        assert BranchingService.evaluate_condition(
            "age >= 18",
            context
        ) is False

        # Multiple conditions (simulating 'in' with 'or')
        context = {"zip": "98101", "wants_email": "true"}
        assert BranchingService.evaluate_condition(
            "(zip == '98101' or zip == '98102') and wants_email == 'true'",
            context
        ) is True

    def test_determine_next_step_no_conditionals(self):
        """Test determine_next_step with no conditionals."""
        step = SurveyStep(
            id="ask_name",
            text="Name?",
            type=QuestionType.TEXT,
            next="ask_age"
        )

        next_id = BranchingService.determine_next_step(step, {})
        assert next_id == "ask_age"

    def test_determine_next_step_conditional_matches(self):
        """Test determine_next_step when conditional matches."""
        step = SurveyStep(
            id="ask_volunteer",
            text="Volunteer?",
            type=QuestionType.TEXT,
            next_conditional=[
                ConditionalNext(
                    condition="wants_volunteer == 'true'",
                    next="ask_email"
                )
            ],
            next="ask_phone"
        )

        # Conditional matches
        context = {"wants_volunteer": "true"}
        next_id = BranchingService.determine_next_step(step, context)
        assert next_id == "ask_email"

        # Conditional doesn't match, use default
        context = {"wants_volunteer": "false"}
        next_id = BranchingService.determine_next_step(step, context)
        assert next_id == "ask_phone"

    def test_determine_next_step_multiple_conditionals(self):
        """Test determine_next_step with multiple conditionals (first match wins)."""
        step = SurveyStep(
            id="ask_age",
            text="Age?",
            type=QuestionType.TEXT,
            next_conditional=[
                ConditionalNext(condition="age < 18", next="minor_path"),
                ConditionalNext(condition="age < 65", next="adult_path"),
                ConditionalNext(condition="age >= 65", next="senior_path"),
            ],
            next="default_path"
        )

        # First condition matches
        next_id = BranchingService.determine_next_step(step, {"age": 16})
        assert next_id == "minor_path"

        # Second condition matches
        next_id = BranchingService.determine_next_step(step, {"age": 30})
        assert next_id == "adult_path"

        # Third condition matches
        next_id = BranchingService.determine_next_step(step, {"age": 70})
        assert next_id == "senior_path"

    def test_determine_next_step_invalid_condition_skipped(self):
        """Test that invalid conditions are skipped with warning."""
        step = SurveyStep(
            id="ask",
            text="?",
            type=QuestionType.TEXT,
            next_conditional=[
                ConditionalNext(
                    condition="undefined_var == 'test'",  # Will fail
                    next="path1"
                ),
                ConditionalNext(
                    condition="age > 18",  # Valid
                    next="path2"
                )
            ],
            next="default_path"
        )

        # Invalid condition skipped, valid one evaluated
        next_id = BranchingService.determine_next_step(step, {"age": 25})
        assert next_id == "path2"

    def test_determine_next_step_all_conditions_fail(self):
        """Test that default next is used when no conditions match."""
        step = SurveyStep(
            id="ask",
            text="?",
            type=QuestionType.TEXT,
            next_conditional=[
                ConditionalNext(condition="age < 18", next="minor"),
                ConditionalNext(condition="age > 65", next="senior"),
            ],
            next="adult"
        )

        next_id = BranchingService.determine_next_step(step, {"age": 30})
        assert next_id == "adult"

    def test_determine_next_step_no_next_raises_error(self):
        """Test that missing next raises error."""
        step = SurveyStep(
            id="ask",
            text="?",
            type=QuestionType.TEXT,
            next_conditional=[
                ConditionalNext(condition="age < 18", next="minor")
            ]
            # Missing default next
        )

        # When condition doesn't match and no default next
        with pytest.raises(BranchingError, match="No valid next"):
            BranchingService.determine_next_step(step, {"age": 30})

    def test_safe_evaluation_no_code_execution(self):
        """Test that simpleeval prevents code execution."""
        # These should all fail safely
        dangerous_expressions = [
            "__import__('os').system('ls')",
            "exec('print(1)')",
            "eval('1+1')",
        ]

        for expr in dangerous_expressions:
            with pytest.raises(BranchingError):
                BranchingService.evaluate_condition(expr, {})
