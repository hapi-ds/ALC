"""Property-based tests for discrepancy severity fallback.

Tests Property 17: Discrepancy severity fallback from the
multimodal-knowledge-base design document.

Property 17 validates that for any discrepancy when the Chat_Model fails:
- Severity defaults to "major" when the model returns None or an
  unparseable response (Requirement 9.4).
- Recommendation defaults to a generic text ("Manual review is required
  for this discrepancy.") when the model fails (Requirement 9.9).
- The fallback values are always consistent regardless of input.

**Validates: Requirements 9.4, 9.9**

References:
    - Design: .kiro/specs/Step_4-4_multimodal-knowledge-base/design.md (Property 17)
    - Requirements: .kiro/specs/Step_4-4_multimodal-knowledge-base/requirements.md
    - Implementation: src/backend/src/alcoabase/services/alignment_service.py
"""

from __future__ import annotations

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.alignment_service import (
    _RECOMMENDATION_FALLBACK,
    _SEVERITY_FALLBACK,
    resolve_recommendation,
    resolve_severity,
)


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


def st_failed_model_response() -> st.SearchStrategy[str | None]:
    """Generate model responses that represent failures.

    Failures include None, empty strings, and whitespace-only strings.

    Returns:
        Strategy producing None or empty/whitespace strings.
    """
    return st.one_of(
        st.none(),
        st.just(""),
        st.text(alphabet=" \t\n\r", min_size=0, max_size=20),
    )


def st_unparseable_response() -> st.SearchStrategy[str]:
    """Generate non-empty model responses that don't contain valid severity keywords.

    These represent cases where the model returns something but it cannot
    be parsed into a valid severity classification.

    Returns:
        Strategy producing strings without CRITICAL, MAJOR, or MINOR.
    """
    return st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N", "P", "Z"),
        ),
        min_size=1,
        max_size=200,
    ).filter(
        lambda s: s.strip()
        and "CRITICAL" not in s.upper()
        and "MAJOR" not in s.upper()
        and "MINOR" not in s.upper()
    )


def st_valid_severity_response() -> st.SearchStrategy[tuple[str, str]]:
    """Generate model responses containing valid severity keywords.

    Returns tuples of (response_text, expected_severity).

    Returns:
        Strategy producing (response, expected_severity) pairs.
    """
    return st.one_of(
        st.tuples(
            st.from_regex(r".*CRITICAL.*", fullmatch=True).map(
                lambda s: s if "MINOR" not in s.upper() else "CRITICAL"
            ),
            st.just("critical"),
        ),
        st.tuples(
            st.just("MINOR"),
            st.just("minor"),
        ),
        st.tuples(
            st.just("MAJOR"),
            st.just("major"),
        ),
    )


def st_discrepancy_description() -> st.SearchStrategy[str]:
    """Generate random discrepancy descriptions.

    Returns:
        Strategy producing non-empty strings representing discrepancy text.
    """
    return st.text(min_size=1, max_size=500).filter(lambda s: s.strip())


def st_recommendation_text() -> st.SearchStrategy[str]:
    """Generate non-empty recommendation text from a model.

    Returns:
        Strategy producing non-empty strings representing recommendations.
    """
    return st.text(min_size=1, max_size=1000).filter(lambda s: s.strip())


# ---------------------------------------------------------------------------
# Property 17: Discrepancy severity fallback
# ---------------------------------------------------------------------------


class TestSeverityFallback:
    """Property tests for severity fallback when Chat_Model fails.

    When the Chat_Model fails to classify severity (returns None, empty,
    or unparseable response), the system SHALL default to "major".

    **Validates: Requirements 9.4, 9.9**
    """

    @given(response=st_failed_model_response())
    @settings(max_examples=200)
    def test_severity_defaults_to_major_on_model_failure(
        self,
        response: str | None,
    ) -> None:
        """When Chat_Model returns None or empty, severity defaults to "major".

        **Validates: Requirements 9.4**
        """
        result = resolve_severity(response)

        assert result == "major", (
            f"Expected severity 'major' on model failure, got '{result}' "
            f"for response={response!r}"
        )

    @given(response=st_unparseable_response())
    @settings(max_examples=200)
    def test_severity_defaults_to_major_on_unparseable_response(
        self,
        response: str,
    ) -> None:
        """When Chat_Model returns unparseable text, severity defaults to "major".

        **Validates: Requirements 9.4**
        """
        result = resolve_severity(response)

        assert result == "major", (
            f"Expected severity 'major' on unparseable response, got '{result}' "
            f"for response={response!r}"
        )

    @given(response=st_failed_model_response())
    @settings(max_examples=200)
    def test_recommendation_defaults_to_generic_on_model_failure(
        self,
        response: str | None,
    ) -> None:
        """When Chat_Model fails for recommendation, generic text is used.

        **Validates: Requirements 9.9**
        """
        result = resolve_recommendation(response)

        assert result == _RECOMMENDATION_FALLBACK, (
            f"Expected generic recommendation on model failure, got '{result}' "
            f"for response={response!r}"
        )
        assert result == "Manual review is required for this discrepancy."

    @given(response=st_recommendation_text())
    @settings(max_examples=200)
    def test_recommendation_uses_model_response_when_available(
        self,
        response: str,
    ) -> None:
        """When Chat_Model returns valid text, it is used as recommendation.

        **Validates: Requirements 9.9**
        """
        result = resolve_recommendation(response)

        assert result == response.strip()[:500], (
            f"Expected model response (capped at 500 chars), got '{result}' "
            f"for response={response!r}"
        )

    @given(response=st_recommendation_text())
    @settings(max_examples=200)
    def test_recommendation_capped_at_500_characters(
        self,
        response: str,
    ) -> None:
        """Recommendation text is always capped at 500 characters.

        **Validates: Requirements 9.9**
        """
        result = resolve_recommendation(response)

        assert len(result) <= 500, (
            f"Recommendation exceeds 500 chars: len={len(result)} "
            f"for response of len={len(response)}"
        )

    @given(
        response=st_failed_model_response(),
        description=st_discrepancy_description(),
    )
    @settings(max_examples=200)
    def test_fallback_values_are_consistent(
        self,
        response: str | None,
        description: str,
    ) -> None:
        """Fallback values are always the same regardless of discrepancy content.

        The fallback severity is always "major" and the fallback recommendation
        is always the same generic text, no matter what the discrepancy
        description contains.

        **Validates: Requirements 9.4, 9.9**
        """
        severity = resolve_severity(response)
        recommendation = resolve_recommendation(response)

        # Severity is always "major" on failure
        assert severity == _SEVERITY_FALLBACK
        assert severity == "major"

        # Recommendation is always the generic text on failure
        assert recommendation == _RECOMMENDATION_FALLBACK
        assert recommendation == "Manual review is required for this discrepancy."

    @given(data=st.data())
    @settings(max_examples=200)
    def test_severity_parses_valid_keywords_correctly(
        self,
        data: st.DataObject,
    ) -> None:
        """When Chat_Model returns a valid keyword, it is parsed correctly.

        This ensures the fallback is only triggered on actual failures,
        not on valid responses.

        **Validates: Requirements 9.4**
        """
        keyword = data.draw(
            st.sampled_from(["CRITICAL", "MAJOR", "MINOR"]),
            label="keyword",
        )
        # Wrap keyword in random padding
        prefix = data.draw(
            st.text(
                alphabet=st.characters(whitelist_categories=("L", "N", "Z")),
                min_size=0,
                max_size=20,
            ),
            label="prefix",
        )
        suffix = data.draw(
            st.text(
                alphabet=st.characters(whitelist_categories=("L", "N", "Z")),
                min_size=0,
                max_size=20,
            ),
            label="suffix",
        )

        response = f"{prefix}{keyword}{suffix}"
        result = resolve_severity(response)

        expected = keyword.lower()
        assert result == expected, (
            f"Expected severity '{expected}' for response containing "
            f"'{keyword}', got '{result}' (full response: {response!r})"
        )
