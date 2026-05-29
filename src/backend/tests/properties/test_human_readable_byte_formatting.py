"""Property-based tests for human-readable byte formatting.

Property 5: Human-Readable Byte Formatting
For any non-negative integer representing bytes, the format_bytes_human_readable
function SHALL produce a string using binary units (KB, MB, GB, TB) rounded to
two decimal places, such that parsing the numeric portion and multiplying by the
unit factor yields a value within 0.01 of the original byte count divided by the
unit factor.

**Validates: Requirements 5.1**

References:
    - Design: .kiro/specs/Step_6-2_admin-system-configuration/design.md
    - Requirements: .kiro/specs/Step_6-2_admin-system-configuration/requirements.md
    - Implementation: src/backend/src/alcoabase/services/storage_quota.py
"""

import re

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.storage_quota import StorageQuotaService

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

UNIT_FACTORS = {
    "B": 1,
    "KB": 1024**1,
    "MB": 1024**2,
    "GB": 1024**3,
    "TB": 1024**4,
}

VALID_UNITS = {"B", "KB", "MB", "GB", "TB"}

# Regex to parse the output format: "<number> <unit>"
FORMAT_PATTERN = re.compile(r"^(\d+(?:\.\d+)?)\s+(B|KB|MB|GB|TB)$")


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


def st_byte_values() -> st.SearchStrategy[int]:
    """Generate non-negative integers representing byte counts.

    Covers the full range from 0 to multi-terabyte values.
    """
    return st.integers(min_value=0, max_value=10 * 1024**4)


def st_nonzero_byte_values() -> st.SearchStrategy[int]:
    """Generate positive integers representing non-zero byte counts.

    Focuses on values that will produce KB, MB, GB, or TB units.
    """
    return st.integers(min_value=1, max_value=10 * 1024**4)


def st_bytes_in_unit_range(unit: str) -> st.SearchStrategy[int]:
    """Generate byte values that fall within a specific unit range.

    Args:
        unit: The target unit (KB, MB, GB, TB).

    Returns:
        Strategy producing byte values that should format to the given unit.
    """
    factor = UNIT_FACTORS[unit]
    # Values from 1*factor to just under the next unit
    next_factors = {"KB": UNIT_FACTORS["MB"], "MB": UNIT_FACTORS["GB"],
                    "GB": UNIT_FACTORS["TB"], "TB": 10 * UNIT_FACTORS["TB"]}
    max_val = next_factors[unit] - 1
    return st.integers(min_value=factor, max_value=max_val)


# ---------------------------------------------------------------------------
# Property 5: Output format is valid (number + binary unit)
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(size_bytes=st_byte_values())
def test_format_produces_valid_format_string(size_bytes: int) -> None:
    """format_bytes_human_readable produces a string matching '<number> <unit>'.

    The output must be parseable as a numeric value followed by a valid
    binary unit (B, KB, MB, GB, TB).

    **Validates: Requirements 5.1**
    """
    result = StorageQuotaService.format_bytes_human_readable(size_bytes)

    match = FORMAT_PATTERN.match(result)
    assert match is not None, (
        f"Output '{result}' does not match expected format '<number> <unit>' "
        f"for input {size_bytes} bytes"
    )

    unit = match.group(2)
    assert unit in VALID_UNITS, (
        f"Unit '{unit}' is not a valid binary unit. "
        f"Expected one of {VALID_UNITS}"
    )


# ---------------------------------------------------------------------------
# Property 5: Numeric portion × unit factor ≈ original bytes
# ---------------------------------------------------------------------------


@settings(max_examples=300)
@given(size_bytes=st_nonzero_byte_values())
def test_format_roundtrip_within_tolerance(size_bytes: int) -> None:
    """Parsing numeric portion × unit factor yields value within 0.01 of original / unit factor.

    For non-zero byte values, the formatted numeric value multiplied by
    the unit factor should reconstruct a value close to the original.
    Specifically, the parsed numeric portion should be within 0.01 of
    (original bytes / unit factor).

    **Validates: Requirements 5.1**
    """
    result = StorageQuotaService.format_bytes_human_readable(size_bytes)

    match = FORMAT_PATTERN.match(result)
    assert match is not None, f"Could not parse output: '{result}'"

    numeric_str = match.group(1)
    unit = match.group(2)
    numeric_value = float(numeric_str)
    unit_factor = UNIT_FACTORS[unit]

    # The expected value is original bytes / unit factor
    expected_value = size_bytes / unit_factor

    # The parsed numeric portion should be within 0.01 of expected
    assert abs(numeric_value - expected_value) <= 0.01, (
        f"Parsed value {numeric_value} is not within 0.01 of expected "
        f"{expected_value} (original={size_bytes}, unit={unit}, factor={unit_factor})"
    )


# ---------------------------------------------------------------------------
# Property 5: Zero bytes produces "0 B"
# ---------------------------------------------------------------------------


def test_zero_bytes_produces_zero_b() -> None:
    """Zero bytes always formats to '0 B'.

    **Validates: Requirements 5.1**
    """
    result = StorageQuotaService.format_bytes_human_readable(0)
    assert result == "0 B", f"Expected '0 B' for 0 bytes, got '{result}'"


# ---------------------------------------------------------------------------
# Property 5: Correct unit selection based on magnitude
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(size_bytes=st_bytes_in_unit_range("KB"))
def test_kb_range_uses_kb_unit(size_bytes: int) -> None:
    """Values in KB range (1024 to 1048575) use KB unit.

    **Validates: Requirements 5.1**
    """
    result = StorageQuotaService.format_bytes_human_readable(size_bytes)
    match = FORMAT_PATTERN.match(result)
    assert match is not None
    assert match.group(2) == "KB", (
        f"Expected KB unit for {size_bytes} bytes, got '{result}'"
    )


@settings(max_examples=100)
@given(size_bytes=st_bytes_in_unit_range("MB"))
def test_mb_range_uses_mb_unit(size_bytes: int) -> None:
    """Values in MB range (1048576 to 1073741823) use MB unit.

    **Validates: Requirements 5.1**
    """
    result = StorageQuotaService.format_bytes_human_readable(size_bytes)
    match = FORMAT_PATTERN.match(result)
    assert match is not None
    assert match.group(2) == "MB", (
        f"Expected MB unit for {size_bytes} bytes, got '{result}'"
    )


@settings(max_examples=100)
@given(size_bytes=st_bytes_in_unit_range("GB"))
def test_gb_range_uses_gb_unit(size_bytes: int) -> None:
    """Values in GB range (1073741824 to 1099511627775) use GB unit.

    **Validates: Requirements 5.1**
    """
    result = StorageQuotaService.format_bytes_human_readable(size_bytes)
    match = FORMAT_PATTERN.match(result)
    assert match is not None
    assert match.group(2) == "GB", (
        f"Expected GB unit for {size_bytes} bytes, got '{result}'"
    )


@settings(max_examples=100)
@given(size_bytes=st_bytes_in_unit_range("TB"))
def test_tb_range_uses_tb_unit(size_bytes: int) -> None:
    """Values in TB range (1099511627776+) use TB unit.

    **Validates: Requirements 5.1**
    """
    result = StorageQuotaService.format_bytes_human_readable(size_bytes)
    match = FORMAT_PATTERN.match(result)
    assert match is not None
    assert match.group(2) == "TB", (
        f"Expected TB unit for {size_bytes} bytes, got '{result}'"
    )


# ---------------------------------------------------------------------------
# Property 5: Values below 1 KB use bytes unit
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(size_bytes=st.integers(min_value=1, max_value=1023))
def test_sub_kb_uses_bytes_unit(size_bytes: int) -> None:
    """Values below 1024 bytes use the B (bytes) unit without decimals.

    **Validates: Requirements 5.1**
    """
    result = StorageQuotaService.format_bytes_human_readable(size_bytes)
    match = FORMAT_PATTERN.match(result)
    assert match is not None
    assert match.group(2) == "B", (
        f"Expected B unit for {size_bytes} bytes, got '{result}'"
    )
    # For raw bytes, the numeric value should equal the input exactly
    assert int(float(match.group(1))) == size_bytes, (
        f"Expected numeric value {size_bytes} for B unit, got {match.group(1)}"
    )


# ---------------------------------------------------------------------------
# Property 5: Output uses exactly 2 decimal places for non-byte units
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(size_bytes=st.integers(min_value=1024, max_value=10 * 1024**4))
def test_non_byte_units_have_two_decimal_places(size_bytes: int) -> None:
    """Non-byte unit outputs are rounded to exactly 2 decimal places.

    **Validates: Requirements 5.1**
    """
    result = StorageQuotaService.format_bytes_human_readable(size_bytes)
    match = FORMAT_PATTERN.match(result)
    assert match is not None

    numeric_str = match.group(1)
    unit = match.group(2)

    if unit != "B":
        # Should have exactly 2 decimal places
        assert "." in numeric_str, (
            f"Expected decimal point in '{numeric_str}' for unit {unit}"
        )
        decimal_part = numeric_str.split(".")[1]
        assert len(decimal_part) == 2, (
            f"Expected 2 decimal places, got {len(decimal_part)} in '{result}'"
        )
