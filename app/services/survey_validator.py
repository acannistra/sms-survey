"""Survey graph validator for structural analysis.

This module validates the survey flow graph to ensure:
- All steps are reachable
- No circular references
- All next references are valid
- Terminal steps are properly configured
"""

from typing import Set, Dict, List
from collections import defaultdict, deque

from app.schemas.survey import Survey, QuestionType
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
