"""Property-based tests for inference mode enum validation.

Property 4: Inference Mode Enum Validation
For any string submitted as the inference_mode value, the system SHALL accept
it if and only if it is exactly one of "gpu", "cpu", or "mock". All other
strings SHALL be rejected with HTTP 422 (ValidationError from Pydantic).

**Validates: Requirements 3.2**

References:
    - Design: .kiro/specs/Step_6-2_admin-system-configuration/design.md
    - Requirements: .kiro/specs/Step_6-2_admin-system-configuration/requirements.md
"""

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings
from pydantic import ValidationError

from alcoabase.schemas.system_config import AIHardwareConfigUpdate

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_INFERENCE_MODES = ("gpu", "cpu", "mock")


# ---------------------------------------------------------------------------
# Property 4: Valid inference modes are accepted
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(
    inference_mode=st.sampled_from(VALID_INFERENCE_MODES),
)
def test_valid_inference_mode_accepted(inference_mode: str) -> None:
    """AIHardwareConfigUpdate SHALL accept inference_mode if and only if it is
    exactly "gpu", "cpu", or "mock".

    **Validates: Requirements 3.2**
    """
    config = AIHardwareConfigUpdate(inference_mode=inference_mode)
    assert config.inference_mode == inference_mode
    assert config.inference_mode in VALID_INFERENCE_MODES


# ---------------------------------------------------------------------------
# Property 4: Invalid inference modes are rejected with ValidationError
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    inference_mode=st.text(
        alphabet=st.characters(min_codepoint=32, max_codepoint=126),
        min_size=1,
        max_size=50,
    ).filter(lambda s: s not in VALID_INFERENCE_MODES),
)
def test_invalid_inference_mode_rejected(inference_mode: str) -> None:
    """AIHardwareConfigUpdate SHALL reject any inference_mode value that is not
    exactly "gpu", "cpu", or "mock" with a ValidationError (HTTP 422).

    **Validates: Requirements 3.2**
    """
    with pytest.raises(ValidationError):
        AIHardwareConfigUpdate(inference_mode=inference_mode)


# ---------------------------------------------------------------------------
# Property 4: Case-sensitive — uppercase/mixed case variants rejected
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(
    base_mode=st.sampled_from(VALID_INFERENCE_MODES),
)
def test_inference_mode_case_sensitive(base_mode: str) -> None:
    """AIHardwareConfigUpdate SHALL reject case variants of valid modes
    (e.g., "GPU", "Cpu", "MOCK") since validation is case-sensitive.

    **Validates: Requirements 3.2**
    """
    # Generate case variants that differ from the original
    variants = [base_mode.upper(), base_mode.capitalize(), base_mode.swapcase()]
    for variant in variants:
        if variant not in VALID_INFERENCE_MODES:
            with pytest.raises(ValidationError):
                AIHardwareConfigUpdate(inference_mode=variant)


# ---------------------------------------------------------------------------
# Property 4: None is accepted (field is optional)
# ---------------------------------------------------------------------------


def test_inference_mode_none_accepted() -> None:
    """AIHardwareConfigUpdate SHALL accept None for inference_mode since the
    field is optional (partial update semantics).

    **Validates: Requirements 3.2**
    """
    config = AIHardwareConfigUpdate(inference_mode=None)
    assert config.inference_mode is None


# ---------------------------------------------------------------------------
# Property 4: Empty string rejected
# ---------------------------------------------------------------------------


def test_inference_mode_empty_string_rejected() -> None:
    """AIHardwareConfigUpdate SHALL reject an empty string for inference_mode
    with a ValidationError.

    **Validates: Requirements 3.2**
    """
    with pytest.raises(ValidationError):
        AIHardwareConfigUpdate(inference_mode="")
