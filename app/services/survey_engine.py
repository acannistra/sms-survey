"""Survey engine for orchestrating survey flow.

This module coordinates all survey components to process user responses,
update state, evaluate branching logic, and render responses.
"""

from typing import Tuple
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models.session import SurveySession
from app.models.response import SurveyResponse
from app.schemas.survey import QuestionType, Survey
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
        survey: Survey,
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
        survey: Survey,
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
