"""Property-based tests for Password Policy Validation Completeness.

Tests Property 2 from the setup-wizard design document, validating that the
PasswordValidator correctly identifies all violated rules for any input string
and rejects if and only if at least one rule is violated.

**Validates: Requirements 3.2, 3.3**

References:
    - Design: .kiro/specs/setup-wizard/design.md (Correctness Property 2)
    - Requirements: .kiro/specs/setup-wizard/requirements.md (Requirements 3.2, 3.3)
"""

import re
import string

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.password_validator import PasswordValidator


# ---------------------------------------------------------------------------
# Constants — mirror the validator's error messages for assertion matching
# ---------------------------------------------------------------------------

ERROR_MIN_LENGTH = "Password must be at least 12 characters long"
ERROR_UPPERCASE = "Password must contain at least one uppercase letter"
ERROR_LOWERCASE = "Password must contain at least one lowercase letter"
ERROR_DIGIT = "Password must contain at least one digit"
ERROR_SPECIAL = "Password must contain at least one special character"


# ---------------------------------------------------------------------------
# Oracle — independently compute which rules a password violates
# ---------------------------------------------------------------------------


def _compute_violations(password: str) -> set[str]:
    """Independently determine which password policy rules are violated.

    This serves as a test oracle — it uses simple, direct checks that
    mirror the policy rules without relying on the validator implementation.

    Args:
        password: The password string to check.

    Returns:
        Set of error message strings for each violated rule.
    """
    violations: set[str] = set()

    if len(password) < 12:
        violations.add(ERROR_MIN_LENGTH)

    if not any(c in string.ascii_uppercase for c in password):
        violations.add(ERROR_UPPERCASE)

    if not any(c in string.ascii_lowercase for c in password):
        violations.add(ERROR_LOWERCASE)

    if not any(c in string.digits for c in password):
        violations.add(ERROR_DIGIT)

    if not any(c not in string.ascii_letters + string.digits for c in password):
        violations.add(ERROR_SPECIAL)

    return violations


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


@st.composite
def st_password_with_controlled_classes(draw: st.DrawFn) -> str:
    """Generate random strings with controlled character class composition.

    This strategy produces strings that may or may not satisfy each individual
    password policy rule, giving good coverage of all violation combinations.

    Returns:
        A random string composed of selectively included character classes.
    """
    # Decide which character classes to include
    include_upper = draw(st.booleans())
    include_lower = draw(st.booleans())
    include_digit = draw(st.booleans())
    include_special = draw(st.booleans())

    # Build the character pool based on included classes
    chars: list[str] = []

    if include_upper:
        chars.extend(draw(st.lists(
            st.sampled_from(list(string.ascii_uppercase)),
            min_size=1,
            max_size=5,
        )))

    if include_lower:
        chars.extend(draw(st.lists(
            st.sampled_from(list(string.ascii_lowercase)),
            min_size=1,
            max_size=5,
        )))

    if include_digit:
        chars.extend(draw(st.lists(
            st.sampled_from(list(string.digits)),
            min_size=1,
            max_size=5,
        )))

    if include_special:
        special_chars = "!@#$%^&*()-_=+[]{}|;:',.<>?/~`"
        chars.extend(draw(st.lists(
            st.sampled_from(list(special_chars)),
            min_size=1,
            max_size=5,
        )))

    # If no classes were included, generate an empty or minimal string
    if not chars:
        # Return empty string to test the "all rules violated" case
        return ""

    # Optionally pad to vary length around the 12-char boundary
    target_length = draw(st.integers(min_value=len(chars), max_value=max(len(chars), 20)))
    while len(chars) < target_length:
        # Pad with characters from the already-included classes
        pool = []
        if include_upper:
            pool.extend(string.ascii_uppercase)
        if include_lower:
            pool.extend(string.ascii_lowercase)
        if include_digit:
            pool.extend(string.digits)
        if include_special:
            pool.extend("!@#$%^&*()-_=+[]{}|;:',.<>?/~`")
        if pool:
            chars.append(draw(st.sampled_from(pool)))
        else:
            break

    # Shuffle to avoid positional bias
    shuffled = draw(st.permutations(chars))
    return "".join(shuffled)


# Also test with fully random text (including unicode)
st_arbitrary_text = st.text(min_size=0, max_size=30)


# ---------------------------------------------------------------------------
# Property 2: Password Policy Validation Completeness
# ---------------------------------------------------------------------------


# Feature: setup-wizard, Property 2: Password Policy Validation Completeness
@settings(max_examples=100)
@given(password=st_password_with_controlled_classes())
def test_password_validation_completeness_controlled(password: str) -> None:
    """For any string with controlled character classes, the validator SHALL
    reject it iff at least one rule is violated, and the error list SHALL
    contain exactly the set of violated rules.

    **Validates: Requirements 3.2, 3.3**
    """
    validator = PasswordValidator()
    errors = validator.validate(password)
    expected_violations = _compute_violations(password)

    # Property: result is empty iff no rules are violated
    if not expected_violations:
        assert errors == [], (
            f"Password '{password}' satisfies all rules but got errors: {errors}"
        )
    else:
        assert errors != [], (
            f"Password '{password}' violates rules {expected_violations} "
            f"but validator returned no errors"
        )

    # Property: number of errors matches number of violated rules
    assert len(errors) == len(expected_violations), (
        f"Password '{password}': expected {len(expected_violations)} errors "
        f"but got {len(errors)}. "
        f"Expected: {expected_violations}, Got: {errors}"
    )

    # Property: each error corresponds to a violated rule (exact set match)
    assert set(errors) == expected_violations, (
        f"Password '{password}': error set mismatch. "
        f"Expected: {expected_violations}, Got: {set(errors)}"
    )


# Feature: setup-wizard, Property 2: Password Policy Validation Completeness
@settings(max_examples=100)
@given(password=st_arbitrary_text)
def test_password_validation_completeness_arbitrary(password: str) -> None:
    """For any arbitrary string input, the validator SHALL reject it iff at
    least one rule is violated, and the error list SHALL contain exactly the
    set of violated rules.

    **Validates: Requirements 3.2, 3.3**
    """
    validator = PasswordValidator()
    errors = validator.validate(password)
    expected_violations = _compute_violations(password)

    # Property: result is empty iff no rules are violated
    if not expected_violations:
        assert errors == [], (
            f"Password '{password}' satisfies all rules but got errors: {errors}"
        )
    else:
        assert errors != [], (
            f"Password '{password}' violates rules {expected_violations} "
            f"but validator returned no errors"
        )

    # Property: number of errors matches number of violated rules
    assert len(errors) == len(expected_violations), (
        f"Password '{password}': expected {len(expected_violations)} errors "
        f"but got {len(errors)}. "
        f"Expected: {expected_violations}, Got: {errors}"
    )

    # Property: each error corresponds to a violated rule (exact set match)
    assert set(errors) == expected_violations, (
        f"Password '{password}': error set mismatch. "
        f"Expected: {expected_violations}, Got: {set(errors)}"
    )
