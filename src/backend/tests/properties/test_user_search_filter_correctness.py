"""Property-based tests for User Search Filter Correctness.

Tests Property 8 from the admin-dashboard-user-management design document,
validating that for any search query string Q and for any user in the company,
the user appears in filtered results if and only if Q is a case-insensitive
substring of the user's username, email, or full_name.

**Validates: Requirements 5.3**

References:
    - Design: .kiro/specs/Step_6-1_admin-dashboard-user-management/design.md (Property 8)
    - Requirements: .kiro/specs/Step_6-1_admin-dashboard-user-management/requirements.md (5.3)
"""

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.user_management import UserManagementService

# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Characters for generating realistic usernames (alphanumeric + _.-  )
USERNAME_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-"

# Characters for generating realistic names (letters + spaces)
NAME_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ "

# Characters for email local parts
EMAIL_LOCAL_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._+-"


@st.composite
def st_username(draw: st.DrawFn) -> str:
    """Generate a valid username (3-100 chars, alphanumeric + _.- )."""
    return draw(
        st.text(
            alphabet=st.sampled_from(list(USERNAME_CHARS)),
            min_size=3,
            max_size=50,
        )
    )


@st.composite
def st_email(draw: st.DrawFn) -> str:
    """Generate a plausible email address."""
    local = draw(
        st.text(
            alphabet=st.sampled_from(list(EMAIL_LOCAL_CHARS)),
            min_size=1,
            max_size=30,
        )
    )
    domain = draw(
        st.text(
            alphabet=st.sampled_from(list("abcdefghijklmnopqrstuvwxyz")),
            min_size=2,
            max_size=15,
        )
    )
    tld = draw(st.sampled_from(["com", "org", "net", "io", "dev"]))
    return f"{local}@{domain}.{tld}"


@st.composite
def st_full_name(draw: st.DrawFn) -> str:
    """Generate a plausible full name (1-200 chars)."""
    return draw(
        st.text(
            alphabet=st.sampled_from(list(NAME_CHARS)),
            min_size=1,
            max_size=60,
        ).filter(lambda s: s.strip())  # Ensure non-whitespace-only
    )


@st.composite
def st_search_query(draw: st.DrawFn) -> str:
    """Generate a non-empty search query string.

    Uses printable characters to simulate realistic search inputs.
    """
    return draw(
        st.text(
            alphabet=st.sampled_from(
                list("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._@+- ")
            ),
            min_size=1,
            max_size=30,
        ).filter(lambda s: s.strip())  # Ensure non-whitespace-only
    )


@st.composite
def st_user_and_query(draw: st.DrawFn) -> tuple[str, str, str, str]:
    """Generate a (username, email, full_name, query) tuple.

    Returns:
        A tuple of user fields and a search query for testing.
    """
    username = draw(st_username())
    email = draw(st_email())
    full_name = draw(st_full_name())
    query = draw(st_search_query())
    return (username, email, full_name, query)


@st.composite
def st_user_with_substring_query(draw: st.DrawFn) -> tuple[str, str, str, str]:
    """Generate a user and a query that IS a substring of one of the fields.

    This ensures we test the positive case: query is guaranteed to match.

    Returns:
        A tuple of (username, email, full_name, query) where query is a
        case-insensitive substring of at least one field.
    """
    username = draw(st_username())
    email = draw(st_email())
    full_name = draw(st_full_name())

    # Pick one of the three fields to extract a substring from
    field = draw(st.sampled_from([username, email, full_name]))

    # Extract a random substring from the chosen field
    if len(field) == 0:
        query = field
    else:
        start = draw(st.integers(min_value=0, max_value=max(0, len(field) - 1)))
        end = draw(st.integers(min_value=start + 1, max_value=len(field)))
        query = field[start:end]

    # Optionally change case to test case-insensitivity
    case_transform = draw(st.sampled_from(["lower", "upper", "original"]))
    if case_transform == "lower":
        query = query.lower()
    elif case_transform == "upper":
        query = query.upper()

    return (username, email, full_name, query)


# ---------------------------------------------------------------------------
# Property 8: User Search Filter Correctness
# ---------------------------------------------------------------------------


@settings(max_examples=500, deadline=None)
@given(data=st_user_and_query())
def test_search_filter_iff_case_insensitive_substring(
    data: tuple[str, str, str, str],
) -> None:
    """For any user and search query Q, the user appears in filtered results
    if and only if Q is a case-insensitive substring of username, email,
    or full_name.

    **Validates: Requirements 5.3**
    """
    username, email, full_name, query = data

    # Use the service's pure search matching function
    result = UserManagementService.matches_search_query(
        username=username,
        email=email,
        full_name=full_name,
        query=query,
    )

    # Compute expected result: case-insensitive substring match
    q_lower = query.lower()
    expected = (
        q_lower in username.lower()
        or q_lower in email.lower()
        or q_lower in full_name.lower()
    )

    assert result == expected, (
        f"Search filter mismatch for query='{query}'. "
        f"username='{username}', email='{email}', full_name='{full_name}'. "
        f"Got {result}, expected {expected}."
    )


@settings(max_examples=300, deadline=None)
@given(data=st_user_with_substring_query())
def test_search_filter_matches_when_query_is_substring(
    data: tuple[str, str, str, str],
) -> None:
    """For any user and a query that is a substring of one of the user's
    fields (possibly with different casing), the user SHALL appear in
    filtered results.

    **Validates: Requirements 5.3**
    """
    username, email, full_name, query = data

    result = UserManagementService.matches_search_query(
        username=username,
        email=email,
        full_name=full_name,
        query=query,
    )

    assert result is True, (
        f"Expected match for query='{query}' which is a substring of one of: "
        f"username='{username}', email='{email}', full_name='{full_name}'. "
        f"But got no match."
    )


@settings(max_examples=300, deadline=None)
@given(
    username=st_username(),
    email=st_email(),
    full_name=st_full_name(),
)
def test_search_filter_case_insensitive(
    username: str,
    email: str,
    full_name: str,
) -> None:
    """For any user, searching with the username in different cases SHALL
    always match (case-insensitivity property).

    **Validates: Requirements 5.3**
    """
    # The username itself should always match
    assert UserManagementService.matches_search_query(
        username=username,
        email=email,
        full_name=full_name,
        query=username,
    )

    # The username in all-lowercase should also match
    assert UserManagementService.matches_search_query(
        username=username,
        email=email,
        full_name=full_name,
        query=username.lower(),
    )

    # The username in all-uppercase should also match
    assert UserManagementService.matches_search_query(
        username=username,
        email=email,
        full_name=full_name,
        query=username.upper(),
    )


@settings(max_examples=300, deadline=None)
@given(
    username=st_username(),
    email=st_email(),
    full_name=st_full_name(),
)
def test_search_filter_matches_all_three_fields(
    username: str,
    email: str,
    full_name: str,
) -> None:
    """For any user, searching with the exact username, email, or full_name
    SHALL always return a match.

    **Validates: Requirements 5.3**
    """
    # Username match
    assert UserManagementService.matches_search_query(
        username=username,
        email=email,
        full_name=full_name,
        query=username,
    ), f"Username '{username}' should match itself"

    # Email match
    assert UserManagementService.matches_search_query(
        username=username,
        email=email,
        full_name=full_name,
        query=email,
    ), f"Email '{email}' should match itself"

    # Full name match
    assert UserManagementService.matches_search_query(
        username=username,
        email=email,
        full_name=full_name,
        query=full_name,
    ), f"Full name '{full_name}' should match itself"
