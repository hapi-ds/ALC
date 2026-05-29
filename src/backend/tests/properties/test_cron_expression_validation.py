"""Property-based tests for cron expression validation.

Property 7: Cron Expression Validation
For any string, the validate_cron_expression function SHALL return True if and
only if the string is a syntactically valid 5-field cron expression (minute,
hour, day-of-month, month, day-of-week). Invalid syntax, out-of-range values,
and malformed fields SHALL return False.

**Validates: Requirements 7.1, 7.2**

References:
    - Design: .kiro/specs/Step_6-2_admin-system-configuration/design.md
    - Requirements: .kiro/specs/Step_6-2_admin-system-configuration/requirements.md
"""

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.backup_service import BackupService


# ---------------------------------------------------------------------------
# Strategies for generating valid cron fields
# ---------------------------------------------------------------------------

# Field ranges: (min_val, max_val)
_FIELD_RANGES = [
    (0, 59),   # minute
    (0, 23),   # hour
    (1, 31),   # day-of-month
    (1, 12),   # month
    (0, 7),    # day-of-week (0 and 7 are Sunday)
]


def _valid_single_value(min_val: int, max_val: int) -> st.SearchStrategy[str]:
    """Generate a valid single numeric value within range."""
    return st.integers(min_value=min_val, max_value=max_val).map(str)


def _valid_range(min_val: int, max_val: int) -> st.SearchStrategy[str]:
    """Generate a valid range like '1-5'."""
    return st.tuples(
        st.integers(min_value=min_val, max_value=max_val),
        st.integers(min_value=min_val, max_value=max_val),
    ).filter(lambda t: t[0] <= t[1]).map(lambda t: f"{t[0]}-{t[1]}")


def _valid_step(min_val: int, max_val: int) -> st.SearchStrategy[str]:
    """Generate a valid step like '*/2' or '1-5/2'."""
    base = st.one_of(
        st.just("*"),
        _valid_range(min_val, max_val),
    )
    step = st.integers(min_value=1, max_value=max(1, max_val)).map(str)
    return st.tuples(base, step).map(lambda t: f"{t[0]}/{t[1]}")


def _valid_field(min_val: int, max_val: int) -> st.SearchStrategy[str]:
    """Generate a valid cron field (single value, wildcard, range, step, or list)."""
    single = st.one_of(
        st.just("*"),
        _valid_single_value(min_val, max_val),
        _valid_range(min_val, max_val),
        _valid_step(min_val, max_val),
    )
    # Lists of 1-3 valid parts
    return st.lists(single, min_size=1, max_size=3).map(",".join)


# Strategy for a complete valid 5-field cron expression
valid_cron_expression = st.tuples(
    _valid_field(0, 59),   # minute
    _valid_field(0, 23),   # hour
    _valid_field(1, 31),   # day-of-month
    _valid_field(1, 12),   # month
    _valid_field(0, 7),    # day-of-week
).map(lambda fields: " ".join(fields))


# ---------------------------------------------------------------------------
# Strategies for generating invalid cron expressions
# ---------------------------------------------------------------------------


def _out_of_range_value(min_val: int, max_val: int) -> st.SearchStrategy[str]:
    """Generate a numeric value outside the valid range for a field."""
    return st.one_of(
        st.integers(min_value=max_val + 1, max_value=max_val + 100).map(str),
        st.integers(min_value=min_val - 100, max_value=min_val - 1).map(str),
    )


# Strategy for wrong number of fields (not 5)
wrong_field_count = st.one_of(
    # Too few fields (1-4)
    st.lists(st.just("*"), min_size=1, max_size=4).map(" ".join),
    # Too many fields (6-8)
    st.lists(st.just("*"), min_size=6, max_size=8).map(" ".join),
)

# Strategy for expressions with out-of-range values
out_of_range_expression = st.tuples(
    st.sampled_from(range(5)),  # which field to make invalid
    valid_cron_expression,
).map(lambda t: _replace_field_with_out_of_range(t[0], t[1]))


def _replace_field_with_out_of_range(field_idx: int, expr: str) -> str:
    """Replace one field in a valid cron expression with an out-of-range value."""
    fields = expr.split()
    min_val, max_val = _FIELD_RANGES[field_idx]
    # Use a value above the max range
    fields[field_idx] = str(max_val + 1)
    return " ".join(fields)


# Strategy for malformed fields (non-numeric, bad syntax)
malformed_field_values = st.sampled_from([
    "abc", "1-", "-5", "*/", "/2", "1--5", "**", "1,", ",1",
    "1-5-9", "a-b", "*/0", "1/0", "1-5/0", "", "1..5",
    "1-5-3/2", "foo/bar", "1-5/bar",
])

malformed_expression = st.tuples(
    st.sampled_from(range(5)),  # which field to make malformed
    valid_cron_expression,
).map(lambda t: _replace_field_with_malformed(t[0], t[1]))


def _replace_field_with_malformed(field_idx: int, expr: str) -> str:
    """Replace one field in a valid cron expression with a malformed value."""
    import random
    fields = expr.split()
    malformed_options = [
        "abc", "1-", "-5", "*/", "/2", "1--5", "**", "1,", ",1",
        "1-5-9", "a-b", "*/0", "1/0", "1-5/0", "", "1..5",
    ]
    fields[field_idx] = random.choice(malformed_options)  # noqa: S311
    return " ".join(fields)


# ---------------------------------------------------------------------------
# Property 7: Valid cron expressions return True
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(expression=valid_cron_expression)
def test_valid_cron_expression_returns_true(expression: str) -> None:
    """validate_cron_expression SHALL return True for any syntactically valid
    5-field cron expression with values within defined ranges.

    **Validates: Requirements 7.1, 7.2**
    """
    result = BackupService.validate_cron_expression(expression)
    assert result is True, f"Expected True for valid cron: '{expression}'"


# ---------------------------------------------------------------------------
# Property 7: Wrong field count returns False
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(expression=wrong_field_count)
def test_wrong_field_count_returns_false(expression: str) -> None:
    """validate_cron_expression SHALL return False when the expression does
    not contain exactly 5 space-separated fields.

    **Validates: Requirements 7.1, 7.2**
    """
    result = BackupService.validate_cron_expression(expression)
    assert result is False, f"Expected False for wrong field count: '{expression}'"


# ---------------------------------------------------------------------------
# Property 7: Out-of-range values return False
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    field_idx=st.sampled_from(range(5)),
    base_expr=valid_cron_expression,
)
def test_out_of_range_values_return_false(field_idx: int, base_expr: str) -> None:
    """validate_cron_expression SHALL return False when any field contains
    a value outside its defined range.

    **Validates: Requirements 7.1, 7.2**
    """
    fields = base_expr.split()
    min_val, max_val = _FIELD_RANGES[field_idx]
    # Replace with a value above max
    fields[field_idx] = str(max_val + 1)
    expression = " ".join(fields)

    result = BackupService.validate_cron_expression(expression)
    assert result is False, f"Expected False for out-of-range: '{expression}'"


# ---------------------------------------------------------------------------
# Property 7: Malformed fields return False
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    field_idx=st.sampled_from(range(5)),
    base_expr=valid_cron_expression,
    malformed=malformed_field_values,
)
def test_malformed_fields_return_false(
    field_idx: int, base_expr: str, malformed: str
) -> None:
    """validate_cron_expression SHALL return False when any field contains
    malformed syntax (non-numeric characters, invalid separators, etc.).

    **Validates: Requirements 7.1, 7.2**
    """
    fields = base_expr.split()
    fields[field_idx] = malformed
    expression = " ".join(fields)

    result = BackupService.validate_cron_expression(expression)
    assert result is False, f"Expected False for malformed field: '{expression}'"


# ---------------------------------------------------------------------------
# Property 7: Random strings are almost never valid cron
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(expression=st.text(min_size=0, max_size=50))
def test_random_strings_validated_correctly(expression: str) -> None:
    """validate_cron_expression SHALL return a boolean for any input string.
    The result SHALL be True if and only if the string is a valid 5-field
    cron expression.

    **Validates: Requirements 7.1, 7.2**
    """
    result = BackupService.validate_cron_expression(expression)
    assert isinstance(result, bool)

    # If it returns True, verify it actually has 5 valid fields
    if result:
        fields = expression.strip().split()
        assert len(fields) == 5, f"True returned for non-5-field: '{expression}'"
        for i, field in enumerate(fields):
            min_val, max_val = _FIELD_RANGES[i]
            # Each field should be parseable as valid cron syntax
            assert _is_valid_cron_field(field, min_val, max_val), (
                f"True returned but field {i} ('{field}') is invalid"
            )


# ---------------------------------------------------------------------------
# Property 7: Empty and whitespace-only strings return False
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(expression=st.from_regex(r"^\s*$", fullmatch=True))
def test_empty_and_whitespace_returns_false(expression: str) -> None:
    """validate_cron_expression SHALL return False for empty strings and
    whitespace-only strings.

    **Validates: Requirements 7.1, 7.2**
    """
    result = BackupService.validate_cron_expression(expression)
    assert result is False


# ---------------------------------------------------------------------------
# Helper for verifying cron field validity (mirrors implementation logic)
# ---------------------------------------------------------------------------


def _is_valid_cron_field(field: str, min_val: int, max_val: int) -> bool:
    """Independent validation of a cron field for test oracle."""
    if not field:
        return False

    parts = field.split(",")
    for part in parts:
        if not _is_valid_cron_part(part, min_val, max_val):
            return False
    return True


def _is_valid_cron_part(part: str, min_val: int, max_val: int) -> bool:
    """Validate a single cron part."""
    if not part:
        return False

    if "/" in part:
        segments = part.split("/")
        if len(segments) != 2:
            return False
        base, step = segments
        if not step.isdigit() or int(step) == 0:
            return False
        if base == "*":
            return True
        return _is_valid_range_or_value(base, min_val, max_val)

    return _is_valid_range_or_value(part, min_val, max_val)


def _is_valid_range_or_value(part: str, min_val: int, max_val: int) -> bool:
    """Validate a range or single value."""
    if part == "*":
        return True

    if "-" in part:
        segments = part.split("-")
        if len(segments) != 2:
            return False
        start_str, end_str = segments
        if not start_str.isdigit() or not end_str.isdigit():
            return False
        start, end = int(start_str), int(end_str)
        if start > end:
            return False
        if start < min_val or end > max_val:
            return False
        return True

    if not part.isdigit():
        return False
    val = int(part)
    return min_val <= val <= max_val
