"""Property-based tests for quota status classification.

Property 6: Quota Status Classification
For any tuple of (usage_bytes, quota_limit_bytes, alert_threshold_pct),
the compute_quota_status function SHALL return:
- "normal" if quota is None OR usage ≤ (threshold/100) × quota
- "quota_warning" if usage > (threshold/100) × quota AND usage ≤ quota
- "quota_exceeded" if usage > quota

These three states are mutually exclusive and exhaustive for all valid inputs.

**Validates: Requirements 5.3, 5.5, 6.3, 6.4**

References:
    - Design: .kiro/specs/Step_6-2_admin-system-configuration/design.md
    - Requirements: .kiro/specs/Step_6-2_admin-system-configuration/requirements.md
"""

import hypothesis.strategies as st
from hypothesis import assume, given, settings

from alcoabase.services.storage_quota import StorageQuotaService


# Strategies for valid inputs
usage_bytes_strategy = st.integers(min_value=0, max_value=10 * 1024**4)  # 0 to 10 TB
quota_bytes_strategy = st.integers(min_value=1, max_value=10 * 1024**4)  # 1 byte to 10 TB
threshold_pct_strategy = st.integers(min_value=1, max_value=99)


# ---------------------------------------------------------------------------
# Property 6: Normal status when no quota configured (quota_bytes is None)
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    usage_bytes=usage_bytes_strategy,
)
def test_compute_quota_status_returns_normal_when_no_quota(
    usage_bytes: int,
) -> None:
    """compute_quota_status SHALL return "normal" when quota_bytes is None,
    regardless of usage.

    **Validates: Requirements 5.3**
    """
    result = StorageQuotaService.compute_quota_status(usage_bytes, None, None)
    assert result == "normal"


# ---------------------------------------------------------------------------
# Property 6: Normal status when usage ≤ threshold% × quota
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    quota_bytes=quota_bytes_strategy,
    threshold_pct=threshold_pct_strategy,
    usage_bytes=usage_bytes_strategy,
)
def test_compute_quota_status_returns_normal_when_below_threshold(
    quota_bytes: int,
    threshold_pct: int,
    usage_bytes: int,
) -> None:
    """compute_quota_status SHALL return "normal" when usage_bytes ≤
    (threshold_pct / 100) × quota_bytes.

    **Validates: Requirements 5.3**
    """
    threshold_bytes = (threshold_pct / 100.0) * quota_bytes
    assume(usage_bytes <= threshold_bytes)

    result = StorageQuotaService.compute_quota_status(usage_bytes, quota_bytes, threshold_pct)
    assert result == "normal"


# ---------------------------------------------------------------------------
# Property 6: Quota warning when usage > threshold% × quota AND ≤ quota
# ---------------------------------------------------------------------------


@st.composite
def warning_zone_inputs(draw: st.DrawFn) -> tuple[int, int, int]:
    """Generate (usage_bytes, quota_bytes, threshold_pct) where usage is in the warning zone.

    The warning zone is: threshold% × quota < usage ≤ quota.
    We generate quota and threshold first, then pick usage in the valid range.
    """
    # threshold_pct < 100 guarantees a non-empty warning zone
    threshold_pct = draw(st.integers(min_value=1, max_value=98))
    quota_bytes = draw(st.integers(min_value=100, max_value=10 * 1024**4))
    threshold_bytes = int((threshold_pct / 100.0) * quota_bytes)
    # usage must be > threshold_bytes AND <= quota_bytes
    # Ensure there's room in the range
    low = threshold_bytes + 1
    high = quota_bytes
    if low > high:
        # Edge case: threshold rounds up to quota, skip
        low = high
    usage_bytes = draw(st.integers(min_value=low, max_value=high))
    return usage_bytes, quota_bytes, threshold_pct


@settings(max_examples=100)
@given(data=warning_zone_inputs())
def test_compute_quota_status_returns_warning_when_above_threshold_below_quota(
    data: tuple[int, int, int],
) -> None:
    """compute_quota_status SHALL return "quota_warning" when usage_bytes >
    (threshold_pct / 100) × quota_bytes AND usage_bytes ≤ quota_bytes.

    **Validates: Requirements 5.5, 6.3**
    """
    usage_bytes, quota_bytes, threshold_pct = data

    result = StorageQuotaService.compute_quota_status(usage_bytes, quota_bytes, threshold_pct)
    assert result == "quota_warning"


# ---------------------------------------------------------------------------
# Property 6: Quota exceeded when usage > quota
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    quota_bytes=quota_bytes_strategy,
    threshold_pct=threshold_pct_strategy,
    usage_bytes=usage_bytes_strategy,
)
def test_compute_quota_status_returns_exceeded_when_above_quota(
    quota_bytes: int,
    threshold_pct: int,
    usage_bytes: int,
) -> None:
    """compute_quota_status SHALL return "quota_exceeded" when usage_bytes >
    quota_bytes.

    **Validates: Requirements 6.4**
    """
    assume(usage_bytes > quota_bytes)

    result = StorageQuotaService.compute_quota_status(usage_bytes, quota_bytes, threshold_pct)
    assert result == "quota_exceeded"


# ---------------------------------------------------------------------------
# Property 6: Mutual exclusivity — exactly one status returned
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    usage_bytes=usage_bytes_strategy,
    quota_bytes=st.one_of(st.none(), quota_bytes_strategy),
    threshold_pct=st.one_of(st.none(), threshold_pct_strategy),
)
def test_compute_quota_status_returns_exactly_one_valid_state(
    usage_bytes: int,
    quota_bytes: int | None,
    threshold_pct: int | None,
) -> None:
    """compute_quota_status SHALL always return exactly one of "normal",
    "quota_warning", or "quota_exceeded" — states are mutually exclusive
    and exhaustive.

    **Validates: Requirements 5.3, 5.5, 6.3, 6.4**
    """
    result = StorageQuotaService.compute_quota_status(usage_bytes, quota_bytes, threshold_pct)

    valid_states = {"normal", "quota_warning", "quota_exceeded"}
    assert result in valid_states


# ---------------------------------------------------------------------------
# Property 6: Exhaustiveness — classification covers all input combinations
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    usage_bytes=usage_bytes_strategy,
    quota_bytes=st.one_of(st.none(), quota_bytes_strategy),
    threshold_pct=st.one_of(st.none(), threshold_pct_strategy),
)
def test_compute_quota_status_classification_is_exhaustive(
    usage_bytes: int,
    quota_bytes: int | None,
    threshold_pct: int | None,
) -> None:
    """For any valid combination of usage, quota, and threshold, the
    classification SHALL be consistent with the defined rules:
    - "normal" if no quota OR usage ≤ threshold% × quota
    - "quota_warning" if usage > threshold% × quota AND ≤ quota
    - "quota_exceeded" if usage > quota

    **Validates: Requirements 5.3, 5.5, 6.3, 6.4**
    """
    result = StorageQuotaService.compute_quota_status(usage_bytes, quota_bytes, threshold_pct)

    if quota_bytes is None:
        assert result == "normal"
    elif usage_bytes > quota_bytes:
        assert result == "quota_exceeded"
    elif threshold_pct is not None and usage_bytes > (threshold_pct / 100.0) * quota_bytes:
        assert result == "quota_warning"
    else:
        assert result == "normal"
