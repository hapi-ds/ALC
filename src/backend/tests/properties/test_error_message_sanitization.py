"""Property-based tests for error message sanitization.

Tests Property 17 from the AI-Driven Change Impact Analysis design document,
validating that sanitized error messages contain the failure category (exception
type) without exposing internal stack traces or implementation details.

The _sanitize_error_message function must:
- Include the exception type name (failure category)
- Not contain newlines (which would indicate stack trace fragments)
- Be truncated to a maximum of 1000 characters
- Not contain "Traceback" or "File " patterns (stack trace indicators)

**Validates: Requirements 6.9**

References:
    - Design: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/design.md (Property 17)
    - Requirements: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/requirements.md (6.9)
    - Implementation: src/backend/src/alcoabase/tasks/impact_analysis_tasks.py
"""

from __future__ import annotations

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.tasks.impact_analysis_tasks import _sanitize_error_message


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


# Common built-in exception types that could occur during impact analysis
EXCEPTION_TYPES: list[type[Exception]] = [
    ValueError,
    TypeError,
    RuntimeError,
    KeyError,
    AttributeError,
    IOError,
    OSError,
    ConnectionError,
    TimeoutError,
    PermissionError,
    FileNotFoundError,
    NotImplementedError,
    IndexError,
    ZeroDivisionError,
    OverflowError,
    MemoryError,
    ImportError,
    UnicodeDecodeError,
]


@st.composite
def st_exception_message(draw: st.DrawFn) -> str:
    """Generate a random exception message string.

    Includes various patterns that might appear in real exceptions,
    including multi-line messages that could contain stack trace fragments.

    Returns:
        A string that could be an exception message.
    """
    # Mix of short messages, long messages, and messages with stack-trace-like content
    strategy = st.one_of(
        # Simple short messages
        st.text(min_size=0, max_size=100),
        # Messages with newlines (simulating stack trace fragments)
        st.text(min_size=1, max_size=50).flatmap(
            lambda prefix: st.text(min_size=1, max_size=200).map(
                lambda suffix: f"{prefix}\n  File \"/app/src/module.py\", line 42\n    {suffix}"
            )
        ),
        # Messages with Traceback patterns
        st.text(min_size=1, max_size=50).map(
            lambda msg: f"Traceback (most recent call last):\n  File \"/app/main.py\"\n{msg}"
        ),
        # Very long messages (to test truncation)
        st.text(min_size=500, max_size=2000),
    )
    return draw(strategy)


@st.composite
def st_random_exception(draw: st.DrawFn) -> Exception:
    """Generate a random exception with a random type and message.

    Returns:
        An Exception instance with a randomly chosen type and message.
    """
    exc_type = draw(st.sampled_from(EXCEPTION_TYPES))
    message = draw(st_exception_message())

    # Some exception types require special constructor args
    if exc_type is UnicodeDecodeError:
        # UnicodeDecodeError needs specific args
        return UnicodeDecodeError("utf-8", b"\xff", 0, 1, message)
    elif exc_type is KeyError:
        return KeyError(message)
    else:
        return exc_type(message)


@st.composite
def st_custom_exception(draw: st.DrawFn) -> Exception:
    """Generate a custom exception class with a random name and message.

    Tests that custom exception types (not just built-ins) are handled.

    Returns:
        An Exception instance of a dynamically created custom type.
    """
    # Generate a valid Python identifier for the class name
    class_name = draw(
        st.from_regex(r"[A-Z][a-zA-Z0-9]{2,30}Error", fullmatch=True)
    )
    message = draw(st_exception_message())

    # Dynamically create a custom exception class
    custom_exc_type = type(class_name, (Exception,), {})
    return custom_exc_type(message)


# ---------------------------------------------------------------------------
# Property 17: Error Message Sanitization
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(exc=st_random_exception())
def test_sanitized_message_contains_exception_type(exc: Exception) -> None:
    """For any exception, the sanitized error message SHALL contain the
    exception type name (failure category).

    **Validates: Requirements 6.9**
    """
    result = _sanitize_error_message(exc)
    exc_type_name = type(exc).__name__

    assert exc_type_name in result, (
        f"Sanitized message does not contain exception type '{exc_type_name}': "
        f"got '{result[:200]}'"
    )


@settings(max_examples=50)
@given(exc=st_random_exception())
def test_sanitized_message_contains_no_newlines(exc: Exception) -> None:
    """For any exception, the sanitized error message SHALL NOT contain
    newline characters (which would indicate stack trace fragments).

    **Validates: Requirements 6.9**
    """
    result = _sanitize_error_message(exc)

    assert "\n" not in result, (
        f"Sanitized message contains newline: '{result[:200]}'"
    )
    assert "\r" not in result, (
        f"Sanitized message contains carriage return: '{result[:200]}'"
    )


@settings(max_examples=50)
@given(exc=st_random_exception())
def test_sanitized_message_max_length(exc: Exception) -> None:
    """For any exception, the sanitized error message SHALL be truncated
    to a maximum of 1000 characters.

    **Validates: Requirements 6.9**
    """
    result = _sanitize_error_message(exc)

    assert len(result) <= 1000, (
        f"Sanitized message exceeds 1000 characters: length={len(result)}"
    )


@settings(max_examples=50)
@given(exc=st_random_exception())
def test_sanitized_message_no_traceback_patterns(exc: Exception) -> None:
    """For any exception, the sanitized error message SHALL NOT contain
    "Traceback" or "File " patterns that indicate stack trace exposure.

    **Validates: Requirements 6.9**
    """
    result = _sanitize_error_message(exc)

    assert "Traceback" not in result, (
        f"Sanitized message contains 'Traceback': '{result[:200]}'"
    )
    assert "File \"" not in result, (
        f"Sanitized message contains 'File \"' pattern: '{result[:200]}'"
    )


@settings(max_examples=50)
@given(exc=st_custom_exception())
def test_sanitized_message_handles_custom_exceptions(exc: Exception) -> None:
    """For any custom exception type, the sanitized error message SHALL
    contain the custom type name and satisfy all sanitization rules.

    **Validates: Requirements 6.9**
    """
    result = _sanitize_error_message(exc)
    exc_type_name = type(exc).__name__

    # Contains exception type
    assert exc_type_name in result, (
        f"Sanitized message does not contain custom type '{exc_type_name}': "
        f"got '{result[:200]}'"
    )
    # No newlines
    assert "\n" not in result and "\r" not in result, (
        f"Sanitized message contains newline characters: '{result[:200]}'"
    )
    # Max length
    assert len(result) <= 1000, (
        f"Sanitized message exceeds 1000 characters: length={len(result)}"
    )
    # No stack trace patterns
    assert "Traceback" not in result, (
        f"Sanitized message contains 'Traceback': '{result[:200]}'"
    )
    assert "File \"" not in result, (
        f"Sanitized message contains 'File \"' pattern: '{result[:200]}'"
    )
