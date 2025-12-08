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
        - Comparison: ==, !=, >, <, >=, <=
        - Boolean: and, or, not
        - Parentheses for grouping

        Note: List/tuple literals and 'in' operator are not supported due to simpleeval limitations.
        Use multiple equality checks with 'or' instead (e.g., "x == 'a' or x == 'b'")

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
        except KeyError as e:
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
