# Survey YAML Format

This directory contains survey definitions in YAML format. Each survey is defined in a separate `.yaml` file.

## Overview

Survey YAML files define the complete flow of an SMS survey, including:
- Consent workflow
- Questions and validation rules
- Conditional branching logic
- Response storage
- Error messages

## Basic Structure

```yaml
survey:
  id: unique_survey_id
  name: "Human-readable Survey Name"
  description: "Description of the survey purpose"
  version: "1.0.0"

consent:
  step_id: consent_request
  text: "Consent message to user"
  accept_values: ["YES", "Y"]
  decline_values: ["NO", "N", "STOP"]
  decline_message: "Message when user declines"

steps:
  - id: step_id
    text: "Question text"
    type: text|regex|choice|terminal
    validation:
      # Validation rules based on type
    error_message: "Error message for invalid input"
    store_as: variable_name
    next: next_step_id

settings:
  max_retry_attempts: 3
  retry_exceeded_message: "Message when retries exceeded"
  timeout_hours: 48
```

## Question Types

### text
Free-form text input with optional length and pattern constraints.

```yaml
- id: q_name
  text: "What's your name?"
  type: text
  validation:
    min_length: 1
    max_length: 50
    pattern: "^[A-Za-z\\s'-]+$"
  error_message: "Please enter a valid name."
  store_as: name
  next: q_next
```

### regex
Input that must match a specific regular expression pattern.

```yaml
- id: q_zip
  text: "What's your zip code?"
  type: regex
  validation:
    pattern: "^\\d{5}$"
  error_message: "Please enter a 5-digit zip code."
  store_as: zip_code
  next: q_next
```

### choice
Multiple choice question with predefined options.

```yaml
- id: q_volunteer
  text: "Would you like to volunteer? Reply 1 for YES or 2 for NO."
  type: choice
  validation:
    choices:
      - value: "1"
        label: "YES"
        store_as: true
      - value: "2"
        label: "NO"
        store_as: false
  error_message: "Please reply 1 for YES or 2 for NO."
  store_as: wants_to_volunteer
  next: q_next
```

### terminal
Final step that ends the survey (no `next` field).

```yaml
- id: thank_you
  text: "Thank you for completing the survey!"
  type: terminal
```

## Conditional Branching

Use `next_conditional` instead of `next` to branch based on previous answers:

```yaml
- id: q_issues
  text: "What issues matter to you?"
  type: text
  store_as: priority_issues
  next_conditional:
    - condition: "wants_to_volunteer == true"
      next: q_email
    - condition: "wants_to_volunteer == false"
      next: thank_you
```

Conditions are Python expressions evaluated with stored variables as context.

## Jinja2 Templates

Use `{{ variable_name }}` to reference previous answers in question text:

```yaml
- id: q_confirm
  text: "Thanks {{ name }}! Is {{ zip_code }} your correct zip code? Reply YES or NO."
  type: choice
  # ...
```

## Validation Rules

### Length Constraints
- `min_length`: Minimum characters required
- `max_length`: Maximum characters allowed

### Pattern Matching
- `pattern`: Regular expression that input must match

### Choices
- `choices`: List of valid options with values and labels
- `store_as`: Value to store when choice is selected

## Best Practices

1. **Use Clear Question Text**: Write questions as if speaking to the user
2. **Provide Helpful Error Messages**: Tell users exactly what format you expect
3. **Keep Surveys Short**: SMS surveys work best with 3-5 questions
4. **Test Conditional Logic**: Verify all branches lead to valid steps
5. **Use Meaningful IDs**: Step IDs should describe the question
6. **Store Important Values**: Use `store_as` for values needed later
7. **Set Appropriate Timeouts**: Consider user engagement patterns

## Common Patterns

### Yes/No Questions
```yaml
type: choice
validation:
  choices:
    - value: "1"
      label: "YES"
      store_as: true
    - value: "2"
      label: "NO"
      store_as: false
```

### Email Collection
```yaml
type: regex
validation:
  pattern: "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$"
error_message: "Please enter a valid email address."
```

### Phone Number Collection
```yaml
type: regex
validation:
  pattern: "^\\d{10}$"
error_message: "Please enter a 10-digit phone number."
```

### Zip Code Collection
```yaml
type: regex
validation:
  pattern: "^\\d{5}$"
error_message: "Please enter a 5-digit zip code."
```

## Troubleshooting

### Survey Not Loading
- Check YAML syntax (indentation must be spaces, not tabs)
- Verify all step IDs referenced in `next` fields exist
- Ensure `survey.id` matches filename (without .yaml extension)

### Validation Not Working
- Escape special regex characters: `\\d` for digits, `\\s` for spaces
- Test regex patterns online before adding to survey
- Check that `type` matches validation rules (regex for patterns, choice for options)

### Conditional Branching Issues
- Verify stored variable names match `store_as` fields
- Test conditions with Python expressions
- Ensure all conditions lead to valid step IDs
- Provide a default `next` field if conditions might not match

## Example Survey

See `example-survey.yaml` in this directory for a complete working example.
