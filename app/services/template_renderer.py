"""Template rendering service using Jinja2.

This module renders survey question text with context variables using Jinja2.
Templates are rendered with StrictUndefined to catch missing variables early.
"""

from typing import Optional
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
