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
