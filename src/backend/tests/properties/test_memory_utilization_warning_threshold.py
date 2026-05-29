"""Property-based tests for memory utilization warning threshold.

Property 14: Memory Utilization Warning Threshold
For any pair of (memory_used_mb, memory_limit_mb) where memory_limit_mb > 0,
the memory warning flag SHALL be set if and only if
memory_used_mb / memory_limit_mb > 0.9.

**Validates: Requirements 13.4**

References:
    - Design: .kiro/specs/Step_6-2_admin-system-configuration/design.md
    - Requirements: .kiro/specs/Step_6-2_admin-system-configuration/requirements.md
"""

import hypothesis.strategies as st
from hypothesis import assume, given, settings

from alcoabase.services.service_registry import ServiceRegistry


# ---------------------------------------------------------------------------
# Property 14: Warning flag set when utilization > 90%
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(
    memory_used_mb=st.floats(
        min_value=0.0, max_value=1_000_000.0, allow_nan=False, allow_infinity=False
    ),
    memory_limit_mb=st.floats(
        min_value=0.01, max_value=1_000_000.0, allow_nan=False, allow_infinity=False
    ),
)
def test_memory_warning_set_when_utilization_exceeds_90_percent(
    memory_used_mb: float,
    memory_limit_mb: float,
) -> None:
    """is_memory_warning SHALL return True when memory_used_mb / memory_limit_mb > 0.9.

    **Validates: Requirements 13.4**
    """
    assume(memory_limit_mb > 0)
    assume(memory_used_mb / memory_limit_mb > 0.9)

    result = ServiceRegistry.is_memory_warning(memory_used_mb, memory_limit_mb)
    assert result is True


# ---------------------------------------------------------------------------
# Property 14: Warning flag NOT set when utilization <= 90%
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(
    memory_used_mb=st.floats(
        min_value=0.0, max_value=1_000_000.0, allow_nan=False, allow_infinity=False
    ),
    memory_limit_mb=st.floats(
        min_value=0.01, max_value=1_000_000.0, allow_nan=False, allow_infinity=False
    ),
)
def test_memory_warning_not_set_when_utilization_at_or_below_90_percent(
    memory_used_mb: float,
    memory_limit_mb: float,
) -> None:
    """is_memory_warning SHALL return False when memory_used_mb / memory_limit_mb <= 0.9.

    **Validates: Requirements 13.4**
    """
    assume(memory_limit_mb > 0)
    assume(memory_used_mb / memory_limit_mb <= 0.9)

    result = ServiceRegistry.is_memory_warning(memory_used_mb, memory_limit_mb)
    assert result is False


# ---------------------------------------------------------------------------
# Property 14: Warning flag is False when memory_limit_mb is None
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    memory_used_mb=st.floats(
        min_value=0.0, max_value=1_000_000.0, allow_nan=False, allow_infinity=False
    ),
)
def test_memory_warning_false_when_limit_is_none(
    memory_used_mb: float,
) -> None:
    """is_memory_warning SHALL return False when memory_limit_mb is None
    (unlimited container).

    **Validates: Requirements 13.4**
    """
    result = ServiceRegistry.is_memory_warning(memory_used_mb, None)
    assert result is False


# ---------------------------------------------------------------------------
# Property 14: Biconditional — warning iff utilization > 0.9
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(
    memory_used_mb=st.floats(
        min_value=0.0, max_value=1_000_000.0, allow_nan=False, allow_infinity=False
    ),
    memory_limit_mb=st.floats(
        min_value=0.01, max_value=1_000_000.0, allow_nan=False, allow_infinity=False
    ),
)
def test_memory_warning_biconditional(
    memory_used_mb: float,
    memory_limit_mb: float,
) -> None:
    """is_memory_warning SHALL return True if and only if
    memory_used_mb / memory_limit_mb > 0.9 (given memory_limit_mb > 0).

    **Validates: Requirements 13.4**
    """
    assume(memory_limit_mb > 0)

    result = ServiceRegistry.is_memory_warning(memory_used_mb, memory_limit_mb)
    expected = (memory_used_mb / memory_limit_mb) > 0.9

    assert result == expected
