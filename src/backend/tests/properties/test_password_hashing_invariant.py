"""Property-based tests for Password Hashing Invariant.

Tests Property 11 from the admin-dashboard-user-management design document,
validating that for any password stored in the system (whether from creation
or reset), the stored value is a valid bcrypt hash and the original plaintext
never appears anywhere in the stored value.

**Validates: Requirements 6.5, 9.2**

References:
    - Design: .kiro/specs/Step_6-1_admin-dashboard-user-management/design.md (Property 11)
    - Requirements: .kiro/specs/Step_6-1_admin-dashboard-user-management/requirements.md (6.5, 9.2)
"""

import re

import bcrypt
import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.password_reset import generate_temporary_password
from alcoabase.services.user_management import UserManagementService

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# bcrypt hash pattern: $2b$ (or $2a$/$2y$) followed by cost factor and 53 base64 chars
BCRYPT_HASH_PATTERN = re.compile(r"^\$2[aby]\$\d{2}\$.{53}$")


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


@st.composite
def st_random_password(draw: st.DrawFn) -> str:
    """Generate a random password string simulating user creation or reset.

    Generates passwords of varying lengths (1–72 chars) using printable
    ASCII characters. The 72-byte limit is bcrypt's inherent maximum.

    Returns:
        A random password string.
    """
    # Use printable ASCII characters (codes 32-126)
    password = draw(
        st.text(
            alphabet=st.characters(min_codepoint=32, max_codepoint=126),
            min_size=1,
            max_size=72,
        )
    )
    return password


# ---------------------------------------------------------------------------
# Property 11: Password Hashing Invariant
# ---------------------------------------------------------------------------


# Feature: Step_6-1_admin-dashboard-user-management, Property 11: Password Hashing Invariant
@settings(max_examples=200, deadline=None)
@given(password=st_random_password())
def test_hash_password_produces_valid_bcrypt_hash(password: str) -> None:
    """For any password passed to UserManagementService._hash_password,
    the returned value SHALL be a valid bcrypt hash string.

    **Validates: Requirements 6.5, 9.2**
    """
    hashed = UserManagementService._hash_password(password)

    # Must match bcrypt hash format
    assert BCRYPT_HASH_PATTERN.match(hashed), (
        f"_hash_password did not produce a valid bcrypt hash. "
        f"Got: '{hashed}' for password of length {len(password)}"
    )


# Feature: Step_6-1_admin-dashboard-user-management, Property 11: Password Hashing Invariant
@settings(max_examples=200, deadline=None)
@given(password=st_random_password())
def test_hash_password_never_stores_plaintext(password: str) -> None:
    """For any password passed to UserManagementService._hash_password,
    the stored value SHALL NOT be the plaintext password itself — it must
    be a bcrypt hash that differs from the original input.

    **Validates: Requirements 6.5, 9.2**
    """
    hashed = UserManagementService._hash_password(password)

    # The stored value must never equal the plaintext password
    assert hashed != password, (
        f"Stored value is identical to the plaintext password! "
        f"Password: '{password}', Stored: '{hashed}'"
    )

    # The stored value must start with bcrypt prefix, not the password
    assert hashed.startswith("$2"), (
        f"Stored value does not start with bcrypt prefix '$2'. "
        f"Got: '{hashed[:10]}...'"
    )

    # For passwords long enough to be meaningful (>= 8 chars),
    # verify the full plaintext does not appear as a substring in the hash
    if len(password) >= 8:
        assert password not in hashed, (
            f"Full plaintext password appears in the hashed value! "
            f"Password: '{password}', Hash: '{hashed}'"
        )


# Feature: Step_6-1_admin-dashboard-user-management, Property 11: Password Hashing Invariant
@settings(max_examples=200, deadline=None)
@given(password=st_random_password())
def test_hash_password_verifies_with_bcrypt(password: str) -> None:
    """For any password hashed by UserManagementService._hash_password,
    bcrypt.checkpw SHALL verify the original password against the hash.

    This confirms the hash is not only well-formed but functionally correct.

    **Validates: Requirements 6.5, 9.2**
    """
    hashed = UserManagementService._hash_password(password)

    # The original password must verify against the produced hash
    assert bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8")), (
        f"bcrypt.checkpw failed to verify the original password against its hash. "
        f"Password length: {len(password)}"
    )


# Feature: Step_6-1_admin-dashboard-user-management, Property 11: Password Hashing Invariant
@settings(max_examples=100, deadline=None)
@given(data=st.data())
def test_generated_temporary_password_hashes_correctly(data: st.DataObject) -> None:
    """For any temporary password generated by generate_temporary_password
    (simulating creation and reset flows), hashing it SHALL produce a valid
    bcrypt hash that does not contain the plaintext.

    **Validates: Requirements 6.5, 9.2**
    """
    # Generate a temporary password as the service would during creation/reset
    temp_password = generate_temporary_password()

    # Hash it using the UserManagementService method
    hashed = UserManagementService._hash_password(temp_password)

    # Must be a valid bcrypt hash
    assert BCRYPT_HASH_PATTERN.match(hashed), (
        f"Temporary password hash is not valid bcrypt. "
        f"Got: '{hashed}'"
    )

    # Plaintext must not appear in hash
    assert temp_password not in hashed, (
        f"Temporary password plaintext appears in hash! "
        f"Password: '{temp_password}', Hash: '{hashed}'"
    )

    # Must verify correctly
    assert bcrypt.checkpw(temp_password.encode("utf-8"), hashed.encode("utf-8")), (
        f"Temporary password failed bcrypt verification against its own hash."
    )
