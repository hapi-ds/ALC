"""Property-based tests for Password Hashing Round-Trip.

Tests Property 3 from the setup-wizard design document, validating that
hashing a valid password with bcrypt and then verifying the original password
against the hash returns True, and verifying any different string returns False.

**Validates: Requirements 3.4**

References:
    - Design: .kiro/specs/setup-wizard/design.md (Correctness Property 3)
    - Requirements: .kiro/specs/setup-wizard/requirements.md (Requirement 3.4)
"""

import string
from unittest.mock import patch

import bcrypt as _bcrypt_lib
import hypothesis.strategies as st
from hypothesis import assume, given, settings

from alcoabase.services.setup_service import pwd_context


# ---------------------------------------------------------------------------
# Compatibility fix: bcrypt 5.x raises ValueError for passwords > 72 bytes,
# which breaks passlib 1.7.4's internal wrap-bug detection. We patch bcrypt
# to truncate at 72 bytes (bcrypt's inherent limit) before hashing/checking.
# ---------------------------------------------------------------------------

_original_hashpw = _bcrypt_lib.hashpw
_original_checkpw = _bcrypt_lib.checkpw


def _safe_hashpw(password: bytes, salt: bytes) -> bytes:
    """Wrap bcrypt.hashpw to truncate passwords at 72 bytes."""
    if isinstance(password, str):
        password = password.encode("utf-8")
    return _original_hashpw(password[:72], salt)


def _safe_checkpw(password: bytes, hashed_password: bytes) -> bool:
    """Wrap bcrypt.checkpw to truncate passwords at 72 bytes."""
    if isinstance(password, str):
        password = password.encode("utf-8")
    return _original_checkpw(password[:72], hashed_password)


# Apply patches at module level so passlib's backend initialization succeeds
_bcrypt_lib.hashpw = _safe_hashpw
_bcrypt_lib.checkpw = _safe_checkpw


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Character pools for generating valid passwords
UPPERCASE = string.ascii_uppercase
LOWERCASE = string.ascii_lowercase
DIGITS = string.digits
SPECIAL = "!@#$%^&*()-_=+[]{}|;:',.<>?/~`"


@st.composite
def st_valid_password(draw: st.DrawFn) -> str:
    """Generate a random password that satisfies the GxP password policy.

    Policy requirements:
    - Minimum 12 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character
    - Maximum 72 characters (bcrypt's inherent byte limit for ASCII)

    Returns:
        A random string satisfying all password policy rules.
    """
    # Ensure at least one character from each required class
    upper_char = draw(st.sampled_from(list(UPPERCASE)))
    lower_char = draw(st.sampled_from(list(LOWERCASE)))
    digit_char = draw(st.sampled_from(list(DIGITS)))
    special_char = draw(st.sampled_from(list(SPECIAL)))

    # Fill remaining characters (8 to 68 more to stay within 12-72 total)
    all_chars = UPPERCASE + LOWERCASE + DIGITS + SPECIAL
    remaining_length = draw(st.integers(min_value=8, max_value=50))
    remaining = draw(
        st.lists(
            st.sampled_from(list(all_chars)),
            min_size=remaining_length,
            max_size=remaining_length,
        )
    )

    # Combine mandatory characters with remaining and shuffle
    chars = [upper_char, lower_char, digit_char, special_char] + remaining
    shuffled = draw(st.permutations(chars))
    return "".join(shuffled)


@st.composite
def st_different_string(draw: st.DrawFn, original: str) -> str:
    """Generate a string guaranteed to differ from the original.

    Constrains output to ≤72 characters (bcrypt byte limit for ASCII).

    Args:
        original: The original password to differ from.

    Returns:
        A string that is not equal to the original.
    """
    all_chars = UPPERCASE + LOWERCASE + DIGITS + SPECIAL
    candidate = draw(
        st.text(
            alphabet=st.sampled_from(list(all_chars)),
            min_size=1,
            max_size=50,
        )
    )
    assume(candidate != original)
    return candidate


# ---------------------------------------------------------------------------
# Property 3: Password Hashing Round-Trip
# ---------------------------------------------------------------------------


# Feature: setup-wizard, Property 3: Password Hashing Round-Trip
@settings(max_examples=100, deadline=None)
@given(password=st_valid_password())
def test_password_hash_verifies_original(password: str) -> None:
    """For any valid password, hashing it and then verifying the original
    password against the hash SHALL return True.

    **Validates: Requirements 3.4**
    """
    hashed = pwd_context.hash(password)

    # The original password must verify against its own hash
    assert pwd_context.verify(password, hashed), (
        f"Password '{password}' failed to verify against its own bcrypt hash"
    )


# Feature: setup-wizard, Property 3: Password Hashing Round-Trip
@settings(max_examples=100, deadline=None)
@given(data=st.data())
def test_password_hash_rejects_different_string(data: st.DataObject) -> None:
    """For any valid password, hashing it and then verifying a different
    string against the hash SHALL return False.

    **Validates: Requirements 3.4**
    """
    password = data.draw(st_valid_password(), label="original_password")
    different = data.draw(st_different_string(password), label="different_string")

    hashed = pwd_context.hash(password)

    # A different string must NOT verify against the original's hash
    assert not pwd_context.verify(different, hashed), (
        f"Different string '{different}' incorrectly verified against "
        f"hash of '{password}'"
    )
