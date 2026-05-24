"""Property-based tests for missing link severity classification.

Tests Property 4 from the multi-agent always-on auditing design document,
validating that severity classification is correct based on combinations
of training and signature presence.

**Validates: Requirements 7.4**

References:
    - Design: .kiro/specs/Step_5-2_multi-agent-always-on-auditing/design.md (Property 4)
    - Requirements: .kiro/specs/Step_5-2_multi-agent-always-on-auditing/requirements.md (7.4)
"""

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.missing_link_service import classify_severity


# ---------------------------------------------------------------------------
# Property 4: Missing link classification
# ---------------------------------------------------------------------------


# Feature: multi-agent-always-on-auditing, Property 4: Both missing yields Critical
@settings(max_examples=200)
@given(data=st.data())
def test_both_missing_yields_critical(data: st.DataObject) -> None:
    """For any document where both training AND signature are missing,
    the severity SHALL be "Critical".

    **Validates: Requirements 7.4**
    """
    result = classify_severity(training_missing=True, signature_missing=True)

    assert result == "Critical", (
        f"Expected 'Critical' when both training and signature are missing, "
        f"got '{result}'"
    )


# Feature: multi-agent-always-on-auditing, Property 4: Only training missing yields Major
@settings(max_examples=200)
@given(data=st.data())
def test_only_training_missing_yields_major(data: st.DataObject) -> None:
    """For any document where only training is missing (signature present),
    the severity SHALL be "Major".

    **Validates: Requirements 7.4**
    """
    result = classify_severity(training_missing=True, signature_missing=False)

    assert result == "Major", (
        f"Expected 'Major' when only training is missing, got '{result}'"
    )


# Feature: multi-agent-always-on-auditing, Property 4: Only signature missing yields Major
@settings(max_examples=200)
@given(data=st.data())
def test_only_signature_missing_yields_major(data: st.DataObject) -> None:
    """For any document where only signature is missing (training present),
    the severity SHALL be "Major".

    **Validates: Requirements 7.4**
    """
    result = classify_severity(training_missing=False, signature_missing=True)

    assert result == "Major", (
        f"Expected 'Major' when only signature is missing, got '{result}'"
    )


# Feature: multi-agent-always-on-auditing, Property 4: Classification over all boolean combinations
@settings(max_examples=200)
@given(
    training_missing=st.booleans(),
    signature_missing=st.booleans(),
)
def test_classification_all_combinations(
    training_missing: bool, signature_missing: bool
) -> None:
    """For any random combination of training/signature presence, the
    classify_severity function SHALL return "Critical" when both are
    missing, and "Major" when exactly one is missing.

    When neither is missing, the document should not appear in the missing
    links list (the function returns "Major" as a fallback, but this case
    is filtered upstream by detect_missing_links).

    **Validates: Requirements 7.4**
    """
    result = classify_severity(training_missing, signature_missing)

    if training_missing and signature_missing:
        assert result == "Critical", (
            f"Expected 'Critical' when both missing, got '{result}'"
        )
    elif training_missing or signature_missing:
        assert result == "Major", (
            f"Expected 'Major' when exactly one missing "
            f"(training_missing={training_missing}, "
            f"signature_missing={signature_missing}), got '{result}'"
        )
    else:
        # Neither missing — function returns "Major" as fallback,
        # but this case is excluded by detect_missing_links upstream.
        # We verify the function doesn't crash and returns a valid string.
        assert result in ("Critical", "Major"), (
            f"Expected a valid severity string, got '{result}'"
        )
