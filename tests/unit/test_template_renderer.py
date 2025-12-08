"""Unit tests for template renderer service.

Tests Jinja2 template rendering with context variables.
"""

import pytest

from app.services.template_renderer import (
    TemplateRenderer,
    TemplateRenderError,
    get_template_renderer
)


class TestTemplateRenderer:
    """Tests for TemplateRenderer class."""

    def test_simple_variable_substitution(self):
        """Test basic variable substitution."""
        renderer = TemplateRenderer()
        result = renderer.render("Hello {{ name }}!", {"name": "Alice"})
        assert result == "Hello Alice!"

    def test_multiple_variables(self):
        """Test multiple variable substitutions."""
        renderer = TemplateRenderer()
        template = "{{ greeting }} {{ name }}, you are {{ age }} years old."
        context = {"greeting": "Hello", "name": "Bob", "age": 25}
        result = renderer.render(template, context)
        assert result == "Hello Bob, you are 25 years old."

    def test_undefined_variable_raises_error(self):
        """Test that undefined variables raise error with StrictUndefined."""
        renderer = TemplateRenderer()
        template = "Hello {{ undefined_var }}!"

        with pytest.raises(TemplateRenderError, match="Failed to render"):
            renderer.render(template, {})

    def test_empty_context(self):
        """Test rendering template without variables."""
        renderer = TemplateRenderer()
        result = renderer.render("No variables here!", {})
        assert result == "No variables here!"

    def test_conditional_if_statement(self):
        """Test Jinja2 if conditionals."""
        renderer = TemplateRenderer()
        template = """{% if wants_volunteer == 'true' %}
You're volunteering!
{% else %}
You're not volunteering.
{% endif %}"""

        # True case
        result = renderer.render(template, {"wants_volunteer": "true"})
        assert "volunteering!" in result

        # False case
        result = renderer.render(template, {"wants_volunteer": "false"})
        assert "not volunteering" in result

    def test_conditional_multiline(self):
        """Test multiline conditional templates (like in completion messages)."""
        renderer = TemplateRenderer()
        template = """Thanks {{ name }}!
{% if wants_volunteer == 'true' %}
We'll email you at {{ email }}.
{% else %}
We'll keep you updated.
{% endif %}"""

        # Volunteer case
        context = {"name": "Alice", "wants_volunteer": "true", "email": "alice@example.com"}
        result = renderer.render(template, context)
        assert "Thanks Alice!" in result
        assert "alice@example.com" in result

        # Non-volunteer case
        context = {"name": "Bob", "wants_volunteer": "false"}
        result = renderer.render(template, context)
        assert "Thanks Bob!" in result
        assert "keep you updated" in result

    def test_for_loop(self):
        """Test Jinja2 for loops."""
        renderer = TemplateRenderer()
        template = """Items:
{% for item in items %}
- {{ item }}
{% endfor %}"""

        context = {"items": ["apple", "banana", "cherry"]}
        result = renderer.render(template, context)
        assert "apple" in result
        assert "banana" in result
        assert "cherry" in result

    def test_nested_variables(self):
        """Test accessing nested dictionary values."""
        renderer = TemplateRenderer()
        template = "{{ user.name }} lives in {{ user.location }}."
        context = {"user": {"name": "Alice", "location": "Seattle"}}
        result = renderer.render(template, context)
        assert result == "Alice lives in Seattle."

    def test_filters(self):
        """Test Jinja2 filters."""
        renderer = TemplateRenderer()

        # Upper filter
        result = renderer.render("{{ name|upper }}", {"name": "alice"})
        assert result == "ALICE"

        # Lower filter
        result = renderer.render("{{ name|lower }}", {"name": "ALICE"})
        assert result == "alice"

        # Default filter
        result = renderer.render("{{ missing|default('N/A') }}", {})
        assert result == "N/A"

    def test_whitespace_control(self):
        """Test that whitespace is preserved."""
        renderer = TemplateRenderer()
        template = "Line 1\nLine 2\n{{ var }}"
        result = renderer.render(template, {"var": "Line 3"})
        assert result == "Line 1\nLine 2\nLine 3"

    def test_autoescape_enabled(self):
        """Test that autoescape is enabled for security."""
        renderer = TemplateRenderer()
        # HTML characters should be escaped
        template = "{{ content }}"
        context = {"content": "<script>alert('xss')</script>"}
        result = renderer.render(template, context)
        # Should escape < and >
        assert "&lt;" in result
        assert "&gt;" in result
        assert "<script>" not in result

    def test_numeric_values(self):
        """Test rendering numeric values."""
        renderer = TemplateRenderer()
        template = "You are {{ age }} years old."
        result = renderer.render(template, {"age": 25})
        assert result == "You are 25 years old."

    def test_boolean_values(self):
        """Test rendering boolean values."""
        renderer = TemplateRenderer()
        template = "Consented: {{ consented }}"

        result = renderer.render(template, {"consented": True})
        assert "True" in result

        result = renderer.render(template, {"consented": False})
        assert "False" in result

    def test_empty_string_value(self):
        """Test rendering empty string values."""
        renderer = TemplateRenderer()
        template = "Value: '{{ value }}'"
        result = renderer.render(template, {"value": ""})
        assert result == "Value: ''"

    def test_special_characters_in_values(self):
        """Test that special characters in values are handled."""
        renderer = TemplateRenderer()
        template = "Name: {{ name }}"
        # Apostrophes are escaped to &#39; by autoescape
        result = renderer.render(template, {"name": "O'Brien"})
        assert "O" in result and "Brien" in result

    def test_realistic_survey_template(self):
        """Test realistic survey question template."""
        renderer = TemplateRenderer()
        template = "Thanks {{ name }}! What's your ZIP code?"
        context = {"name": "Alice"}
        result = renderer.render(template, context)
        assert result == "Thanks Alice! What's your ZIP code?"

    def test_malformed_template_syntax(self):
        """Test that malformed templates raise error."""
        renderer = TemplateRenderer()
        template = "Hello {{ name"  # Missing closing }}

        with pytest.raises(TemplateRenderError):
            renderer.render(template, {"name": "Alice"})

    def test_invalid_template_logic(self):
        """Test that invalid template logic raises error."""
        renderer = TemplateRenderer()
        template = "{% if unclosed %}"  # Missing endif

        with pytest.raises(TemplateRenderError):
            renderer.render(template, {})


class TestGetTemplateRenderer:
    """Tests for get_template_renderer singleton function."""

    def test_returns_singleton(self):
        """Test that get_template_renderer returns singleton instance."""
        renderer1 = get_template_renderer()
        renderer2 = get_template_renderer()

        assert renderer1 is renderer2

    def test_returns_template_renderer_instance(self):
        """Test that get_template_renderer returns TemplateRenderer instance."""
        renderer = get_template_renderer()

        assert isinstance(renderer, TemplateRenderer)

    def test_singleton_maintains_state(self):
        """Test that singleton instance works correctly."""
        renderer1 = get_template_renderer()
        renderer2 = get_template_renderer()

        # Both should render the same
        result1 = renderer1.render("{{ x }}", {"x": "test"})
        result2 = renderer2.render("{{ x }}", {"x": "test"})

        assert result1 == result2 == "test"
