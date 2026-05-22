"""Property-based tests for change reason normalization in WorkflowEngine.

Tests Property 7 (Change reason normalization) from the Workflow Execution &
State Transitions design document.

The normalization logic in WorkflowEngine._record_transition_audit:
- Stores None if the input is None, empty, or whitespace-only
- Strips leading/trailing whitespace
- Truncates to 500 characters after stripping
- Result is always None or a non-empty string with length <= 500

**Validates: Requirements 6.1, 6.2, 6.3**

References:
    - Design: .kiro/specs/Step_3-2_workflow-execution-state-transitions/design.md
    - Requirements: .kiro/specs/Step_3-2_workflow-execution-state-transitions/requirements.md
"""

from unittest.mock import AsyncMock, MagicMock

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.services.workflow_engine import (
    WorkflowEngine,
    WorkflowTransitionAudit,
)


# ---------------------------------------------------------------------------
# Helper: Extract normalization logic for direct testing
# ---------------------------------------------------------------------------


def normalize_change_reason(change_reason: str | None) -> str | None:
    """Replicate the normalization logic from _record_transition_audit.

    This mirrors the exact logic in WorkflowEngine._record_transition_audit:
    - None input -> None
    - Empty/whitespace-only -> None
    - Otherwise: strip whitespace, truncate to 500 chars

    Args:
        change_reason: Raw change reason input.

    Returns:
        Normalized change reason or None.
    """
    normalized_reason: str | None = None
    if change_reason and change_reason.strip():
        normalized_reason = change_reason.strip()[:500]
    return normalized_reason


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


def st_whitespace_only() -> st.SearchStrategy[str]:
    """Generate strings containing only whitespace characters."""
    return st.text(
        alphabet=st.sampled_from(" \t\n\r\v\f"),
        min_size=1,
        max_size=50,
    )


def st_non_whitespace_text() -> st.SearchStrategy[str]:
    """Generate strings that contain at least one non-whitespace character."""
    return st.text(min_size=1, max_size=1000).filter(
        lambda s: s.strip() != ""
    )


# ---------------------------------------------------------------------------
# Property 7: Change reason normalization
# ---------------------------------------------------------------------------


class TestChangeReasonNormalizationProperty:
    """Property tests verifying change reason normalization behavior.

    For any X-Change-Reason header value, the WorkflowEngine SHALL:
    (a) store None if the value is None, empty, or whitespace-only,
    (b) truncate to exactly 500 characters if the trimmed value exceeds 500,
    (c) store the trimmed value as-is if it is between 1 and 500 characters.

    **Validates: Requirements 6.1, 6.2, 6.3**
    """

    @given(input_str=st.text(min_size=0, max_size=1000))
    @settings(max_examples=200)
    def test_result_is_none_or_nonempty_string_within_500(
        self, input_str: str
    ) -> None:
        """For any string input, the normalized result is either None or a
        non-empty string with length <= 500.

        **Validates: Requirements 6.1, 6.2, 6.3**
        """
        result = normalize_change_reason(input_str)

        if result is not None:
            assert isinstance(result, str)
            assert len(result) > 0, "Result must be non-empty if not None"
            assert len(result) <= 500, (
                f"Result length {len(result)} exceeds 500"
            )

    @given(input_val=st.none())
    @settings(max_examples=10)
    def test_none_input_produces_none(self, input_val: None) -> None:
        """If the input is None, the result is None.

        **Validates: Requirements 6.3**
        """
        result = normalize_change_reason(input_val)
        assert result is None

    @given(input_str=st_whitespace_only())
    @settings(max_examples=100)
    def test_whitespace_only_produces_none(self, input_str: str) -> None:
        """If the input is whitespace-only, the result is None.

        **Validates: Requirements 6.3**
        """
        result = normalize_change_reason(input_str)
        assert result is None, (
            f"Expected None for whitespace-only input {input_str!r}, "
            f"got {result!r}"
        )

    @given(input_str=st_non_whitespace_text())
    @settings(max_examples=200)
    def test_non_whitespace_content_produces_stripped_truncated(
        self, input_str: str
    ) -> None:
        """If the input has non-whitespace content, the result is the stripped
        version truncated to 500 if needed.

        **Validates: Requirements 6.1, 6.2**
        """
        result = normalize_change_reason(input_str)

        assert result is not None, (
            f"Expected non-None for input with content: {input_str!r}"
        )

        stripped = input_str.strip()
        expected = stripped[:500]
        assert result == expected, (
            f"Expected {expected!r}, got {result!r} for input {input_str!r}"
        )

    @given(input_str=st.text(min_size=0, max_size=1000))
    @settings(max_examples=200)
    def test_result_never_has_leading_or_trailing_whitespace(
        self, input_str: str
    ) -> None:
        """The result never has leading or trailing whitespace.

        **Validates: Requirements 6.1**
        """
        result = normalize_change_reason(input_str)

        if result is not None:
            assert result == result.strip(), (
                f"Result has leading/trailing whitespace: {result!r}"
            )

    @given(input_str=st.text(min_size=0, max_size=1000))
    @settings(max_examples=200)
    def test_result_length_always_lte_500(self, input_str: str) -> None:
        """The result length is always <= 500.

        **Validates: Requirements 6.2**
        """
        result = normalize_change_reason(input_str)

        if result is not None:
            assert len(result) <= 500, (
                f"Result length {len(result)} exceeds 500 for input "
                f"of length {len(input_str)}"
            )


# ---------------------------------------------------------------------------
# Property 7 (integration): Verify normalization via _record_transition_audit
# ---------------------------------------------------------------------------


class TestChangeReasonNormalizationViaEngine:
    """Property tests verifying that _record_transition_audit applies the
    same normalization logic as the helper function.

    These tests call the actual engine method with a mock session to verify
    the audit entry's change_reason matches the expected normalization.

    **Validates: Requirements 6.1, 6.2, 6.3**
    """

    @given(
        input_str=st.one_of(
            st.none(),
            st.text(min_size=0, max_size=1000),
        )
    )
    @settings(max_examples=200)
    @pytest.mark.asyncio
    async def test_engine_normalization_matches_helper(
        self, input_str: str | None
    ) -> None:
        """The engine's _record_transition_audit normalizes change_reason
        identically to the normalize_change_reason helper.

        **Validates: Requirements 6.1, 6.2, 6.3**
        """
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        engine = WorkflowEngine()

        await engine._record_transition_audit(
            session=session,
            document_id=1,
            user_id=42,
            previous_state="Draft",
            new_state="Review",
            change_reason=input_str,
        )

        session.add.assert_called_once()
        audit_entry = session.add.call_args[0][0]
        assert isinstance(audit_entry, WorkflowTransitionAudit)

        expected = normalize_change_reason(input_str)
        assert audit_entry.change_reason == expected, (
            f"Engine produced {audit_entry.change_reason!r}, "
            f"expected {expected!r} for input {input_str!r}"
        )
